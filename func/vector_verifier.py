from qgis.core import ( # type: ignore
    QgsProject,
    QgsVectorLayer,
    QgsFields,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
    QgsWkbTypes,
    QgsMessageLog,
    Qgis,
    QgsProcessing,
    QgsRectangle,
)

from collections import defaultdict
from itertools   import islice

import processing # type: ignore

from qgis.PyQt.QtCore import QVariant # type: ignore
from qgis.PyQt.QtWidgets import QInputDialog # type: ignore

from .helper_functions import HelperBase


class VectorVerifier:
    """Encapsulates the logic for validating STALP_JT, BRANS_FIRI_GRPM_JT and TRONSON_JT layers.

    Creates two in‑memory layers containing the geometry/attribute errors it detects:
        • erori_stalp  – point layer (errors concerning STALP_JT)
        • erori_brans_tronson – line layer (errors concerning BRANS_FIRI_GRPM_JT or TRONSON_JT)
    Both layers receive four string/int fields:  NUME_LAYER, FID, TIP_EROARE, DETALII.
    At the end they are added to the current group "DE_VERIFICAT" in the QGIS project.
    """

    def __init__ (self, iface):
        self.iface = iface

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------
    def verify(self,
               stalp_layer_name: str = "STALP_JT",
               brans_layer_name: str = "BRANS_FIRI_GRPM_JT",
               tronson_layer_name: str = "TRONSON_JT",
               tolerance: float | None = None) -> None:
        """Runs the full validation routine.

        Parameters
        ----------
        stalp_layer_name, brans_layer_name, tronson_layer_name : str
            The exact layer names present in the QGIS project.
        tolerance : float, optional
            Snapping tolerance in the layer units.  If *None* (default) the
            algorithm falls back to 0.01 × the layer‑coordinate reference
            system unit (≈ 1 cm for metric CRS ≃ EPSG:3844 or EPSG:3857).
        """
        self.helper = HelperBase()
        self._proj = QgsProject.instance()
        self._stalp = self._get_vector(stalp_layer_name, QgsWkbTypes.PointGeometry)
        self._brans = self._get_vector(brans_layer_name, QgsWkbTypes.LineGeometry)
        self._tronson = self._get_vector(tronson_layer_name, QgsWkbTypes.LineGeometry)

        if tolerance is None:
            # loose heuristic
            tolerance = 0.01

        self._tol = tolerance

        # Spatial indices for speed
        self._idx_brans = QgsSpatialIndex(self._brans.getFeatures())
        self._idx_tronson = QgsSpatialIndex(self._tronson.getFeatures())
        self._idx_stalp = QgsSpatialIndex(self._stalp.getFeatures())

        # Prepare error layers
        self._init_error_layers()
        
        # get the values from layer LINIA_JT - DENUM and have the user choose it from a dropdown
        linia_jt_layer = self._proj.mapLayersByName("LINIE_JT")
        if not linia_jt_layer:
            QgsMessageLog.logMessage("Layer 'LINIE_JT' not found in the project", "VectorVerifier", level=Qgis.Critical)
            return
        linia_jt_layer = linia_jt_layer[0]
        linia_jt_values = set()
        for feature in linia_jt_layer.getFeatures():
            denum = feature["DENUM"]
            if denum:
                linia_jt_values.add(denum)
                
        # keep the list deterministic & human-friendly
        linia_jt_choices = sorted(linia_jt_values)

        self.linia_jt_val, ok = QInputDialog.getItem(
            self.iface.mainWindow(),                # parent – QGIS main window
            "Selectează denumirea liniei JT",                # dialog title
            "DENUM:",                               # label
            linia_jt_choices,                       # items shown in the drop-down
            0,                                      # initially selected index
            False                                   # editable?  False = fixed list
        )

        if not ok:          # user hit Cancel or closed the dialog
            return

        # Perform the five groups of checks
        self._rule1_snapping()
        self._rule2_tip_cir_br()
        self._rule3_tip_cir_jt()
        self._rule4_terminal_br()
        self._rule5_terminal_tronson()
        self._rule6_intindere()
        self._rule7_rupere_cond()

        # Commit & add layers to the project
        self._erori_stalp.commitChanges()
        self._erori_line.commitChanges()
        self.helper.add_layer_to_de_verificat(self._erori_stalp)
        self.helper.add_layer_to_de_verificat(self._erori_line)
        

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------
    def _get_vector(self, name: str, expected_geom_type: int) -> QgsVectorLayer:
        layer_list = self._proj.mapLayersByName(name)
        if not layer_list:
            raise ValueError(f"Layer ‘{name}’ not found in the project")
        layer = layer_list[0]
        if QgsWkbTypes.geometryType(layer.wkbType()) != expected_geom_type:
            raise TypeError(
                f"Layer ‘{name}’ has geometry type {QgsWkbTypes.displayString(layer.wkbType())}, "
                f"expected {QgsWkbTypes.displayString(expected_geom_type)}")
        return layer

    def _init_error_layers(self) -> None:
        fields = QgsFields()
        fields.append(QgsField("NUME_LAYER", QVariant.String))
        fields.append(QgsField("FID", QVariant.Int))
        fields.append(QgsField("TIP_EROARE", QVariant.String))
        fields.append(QgsField("DETALII", QVariant.String))

        crs = self._stalp.crs()  # use the point layer CRS for both
        self._erori_stalp = QgsVectorLayer(f"Point?crs={crs.authid()}", "erori_stalp", "memory")
        self._erori_stalp.dataProvider().addAttributes(fields)
        self._erori_stalp.updateFields()
        self._erori_stalp.startEditing()

        self._erori_line = QgsVectorLayer(f"LineString?crs={crs.authid()}", "erori_brans_tronson", "memory")
        self._erori_line.dataProvider().addAttributes(fields)
        self._erori_line.updateFields()
        self._erori_line.startEditing()

    # ------------------------------------------------------------------
    #  Error‑record helpers
    # ------------------------------------------------------------------
    def _add_err_point(self, geom: QgsGeometry, layer_name: str, fid: int, tip: str, det: str):
        f = QgsFeature(self._erori_stalp.fields())
        f.setGeometry(geom)
        f.setAttribute("NUME_LAYER", layer_name)
        f.setAttribute("FID", fid)
        f.setAttribute("TIP_EROARE", tip)
        f.setAttribute("DETALII", det)
        self._erori_stalp.addFeature(f)

    def _add_err_line(self, geom: QgsGeometry, layer_name: str, fid: int, tip: str, det: str):
        f = QgsFeature(self._erori_line.fields())
        f.setGeometry(geom)
        f.setAttribute("NUME_LAYER", layer_name)
        f.setAttribute("FID", fid)
        f.setAttribute("TIP_EROARE", tip)
        f.setAttribute("DETALII", det)
        self._erori_line.addFeature(f)

    # ------------------------------------------------------------------
    #  Geometry utilities
    # ------------------------------------------------------------------
    def _nearest_lines(self, point: QgsPointXY, index: QgsSpatialIndex, layer: QgsVectorLayer):
        ids = index.nearestNeighbor(point, 5)
        for fid in ids:
            feat = layer.getFeature(fid)
            if feat.geometry().distance(QgsGeometry.fromPointXY(point)) <= self._tol:
                yield feat

    # ------------------------------------------------------------------
    #  RULE 1 – snapping of STALP_JT to either BRANS or TRONSON
    # ------------------------------------------------------------------
    def _rule1_snapping(self):

        # ---------------- 1. STALP must touch either BRANS or TRONSON ------------
        for feat in self._stalp.getFeatures():
            pt = feat.geometry().asPoint()                       # STALP is point ✓
            snapped_to_brans   = any(self._nearest_lines(pt,  self._idx_brans,   self._brans))
            snapped_to_tronson = any(self._nearest_lines(pt,  self._idx_tronson, self._tronson))

            if not (snapped_to_brans or snapped_to_tronson):
                self._add_err_point(
                    feat.geometry(), "STALP_JT", feat.id(),
                    "STALP fără legătură",
                    "Nu este ‘snapped’ nici la BRANS_FIRI_GRPM_JT, nici la TRONSON_JT"
                )

        # ------- helper: stream every vertex of a (multi)-line, one by one -------
        def _vertices(g):
            """Yield all vertex points from a (multi)-LineString geometry."""
            if g.isMultipart():
                for part in g.asMultiPolyline():
                    for v in part:
                        yield v
            else:
                for v in g.asPolyline():
                    yield v
            # If you’re on QGIS ≥3.34 you can replace the whole block with:
            #   yield from g.vertices()

        # ---------------- 2. each BRANS must snap to at least one STALP ----------
        for feat in self._brans.getFeatures():
            if feat["TIP_COND"].upper() != "ACYABY 4x16":
                snapped = False
                for v in _vertices(feat.geometry()):
                    if any(self._nearest_lines(v, self._idx_stalp, self._stalp)):
                        snapped = True
                        break                        # one hit is enough
                if not snapped:
                    self._add_err_line(
                        feat.geometry(), "BRANS_FIRI_GRPM_JT", feat.id(),
                        "BRANS fără legătură",
                        "Nu este ‘snapped’ la STALP_JT"
                    )

        # ---------------- 3. each TRONSON must snap to at least one STALP -------
        for feat in self._tronson.getFeatures():
            snapped = False
            for v in _vertices(feat.geometry()):
                if any(self._nearest_lines(v, self._idx_stalp, self._stalp)):
                    snapped = True
                    break
            if not snapped:
                self._add_err_line(
                    feat.geometry(), "TRONSON_JT", feat.id(),
                    "TRONSON fără legătură",
                    "Nu este ‘snapped’ la STALP_JT"
                )


    # ------------------------------------------------------------------
    #  RULE 2 – TIP_CIR ↔ ‘BR’ consistency
    # ------------------------------------------------------------------
    def _rule2_tip_cir_br(self):
        for feat in self._stalp.getFeatures():
            pt = feat.geometry().asPoint()
            intersects_br = any(self._nearest_lines(pt, self._idx_brans, self._brans))
            tip_cir: str = feat["TIP_CIR"] or ""
            has_br = "BR" in tip_cir.upper()

            if intersects_br and not has_br:
                self._add_err_point(feat.geometry(), "STALP_JT", feat.id(),
                                    "TIP_CIR lipsă BR",
                                    "Intersecție cu BRANS_FIRI_GRPM_JT dar ‘BR’ nu este inclus în TIP_CIR")
            if (not intersects_br) and has_br:
                self._add_err_point(feat.geometry(), "STALP_JT", feat.id(),
                                    "TIP_CIR conține BR fără intersecție",
                                    "‘BR’ prezent în TIP_CIR dar nu intersectează BRANS_FIRI_GRPM_JT")

    # ------------------------------------------------------------------
    #  RULE 3 – TIP_CIR ↔ ‘JT’ consistency (numeric DENUM on TRONSON)
    # ------------------------------------------------------------------
    def _rule3_tip_cir_jt(self):
        for feat in self._stalp.getFeatures():
            pt = feat.geometry().asPoint()
            jtronson_feats = [tr for tr in self._nearest_lines(pt, self._idx_tronson, self._tronson)
                              if self._denum_is_numeric(feat["DENUM"])]
            intersects_jt = bool(jtronson_feats)
            tip_cir: str = feat["TIP_CIR"] or ""
            has_jt = "JT" in tip_cir.upper()

            if intersects_jt and not has_jt:
                self._add_err_point(feat.geometry(), "STALP_JT", feat.id(),
                                    "TIP_CIR lipsă JT",
                                    "Intersectează TRONSON_JT cu DENUM numeric, dar ‘JT’ lipsește din TIP_CIR")
            if (not intersects_jt) and has_jt:
                self._add_err_point(feat.geometry(), "STALP_JT", feat.id(),
                                    "TIP_CIR conține JT fără intersecție",
                                    "‘JT’ în TIP_CIR dar nu intersectează TRONSON_JT numeric")

    @staticmethod
    def _denum_is_numeric(value) -> bool:
        return str(value).isalnum() and not any(ch.isalpha() for ch in str(value))

    # ------------------------------------------------------------------
    #  RULE 4 – terminal BRANS endpoints & TIP_LEG_JT
    # ------------------------------------------------------------------
    def _rule4_terminal_br(self):
        # Determine BRANS endpoints that are not shared with another line
        end_pts = {}
        for feat in self._brans.getFeatures():
            geom = feat.geometry()
            start_pt = QgsPointXY(geom.constGet().pointN(0))
            end_pt = QgsPointXY(geom.constGet().pointN(geom.constGet().numPoints() - 1))
            for p in (start_pt, end_pt):
                key = (round(p.x(), 6), round(p.y(), 6))
                end_pts[key] = end_pts.get(key, 0) + 1

        terminal_coords = {k for k, v in end_pts.items() if v == 1}  # degree 1 -> terminal

        for feat in self._stalp.getFeatures():
            pt = feat.geometry().asPoint()
            snapped_to_terminal_br = False
            for coord in terminal_coords:
                term_pt = QgsPointXY(*coord)
                if QgsGeometry.fromPointXY(term_pt).distance(QgsGeometry.fromPointXY(pt)) <= self._tol:
                    snapped_to_terminal_br = True
                    break
            if snapped_to_terminal_br and str(feat["TIP_LEG_JT"]).strip().lower() in ["t", "t/d"] and self._contains_letters(feat["DENUM"]):
                self._add_err_point(feat.geometry(), "STALP_JT", feat.id(),
                                    "Terminal BR greșit",
                                    "STÂLP terminal cu litere în DENUM pe BRANS și TIP_LEG_JT = t / t/d")

    @staticmethod
    def _contains_letters(val) -> bool:
        return any(ch.isalpha() for ch in str(val))

    # ------------------------------------------------------------------
    #  RULE 5 – dangling TRONSON endpoints need ‘t’ or ‘t/d’ on STALP
    #           + complain when the endpoint touches a single BRANS whose
    #             TIP_FIRI_BR is BMPM/BMPT
    # ------------------------------------------------------------------
    def _rule5_terminal_tronson(self):
        allowed_cond = {
            "tyir 16al + 25al",
            "tyir 3x25al + 16al",
            "tyir 2x25al",
        }

        tol  = self._tol
        tron = self._tronson
        poles = self._stalp

        # ---------- 0. speed helpers ----------
        get_pole     = poles.getFeature
        get_tronson  = tron.getFeature

        # ---------- 1. map TRONSON id -> its two end-points ----------
        tron_endpts = {}                          # fid -> {QgsPointXY, QgsPointXY}
        for f in tron.getFeatures():
            g = f.geometry().constGet()
            tron_endpts[f.id()] = (
                QgsPointXY(g.pointN(0)),
                QgsPointXY(g.pointN(g.numPoints()-1)),
            )

        # ---------- 1.5. orphan-endpoint sweep (capăt de TRONSON fără STÂLP) ----------
        for tid, (p0, p1) in tron_endpts.items():
            for pt in (p0, p1):
                #  a tiny bbox query keeps the candidate list microscopic
                bb_ids = self._idx_stalp.intersects(QgsRectangle(
                    pt.x() - tol, pt.y() - tol, pt.x() + tol, pt.y() + tol))

                has_pole = any(
                    poles.getFeature(pid).geometry().intersects(
                        QgsGeometry.fromPointXY(pt))
                    for pid in bb_ids
                )

                if not has_pole:
                    self._add_err_line(
                        QgsGeometry.fromPointXY(pt), "TRONSON_JT", tid,
                        "Sfârșit tronson fără STÂLP",
                        "Capăt de TRONSON fără STALP_JT corespunzător",
                    )

        # ---------- 2. map STALP id -> [intersecting TRONSON ids] ----------
        poles_touching = defaultdict(list)
        for tf in tron.getFeatures():
            bb = tf.geometry().boundingBox()
            for pid in self._idx_stalp.intersects(bb):
                pf = get_pole(pid)
                if tf.geometry().intersects(pf.geometry()):
                    poles_touching[pid].append(tf.id())

        # ---------- 3. evaluate each pole that has exactly one hit ----------
        for pid, tron_ids in poles_touching.items():
            if len(tron_ids) != 1:
                continue                                    # pole is a node, not a terminal

            tid  = tron_ids[0]
            pf   = get_pole(pid)
            tf   = get_tronson(tid)

            pole_geom   = pf.geometry()
            t_end_0, t_end_1 = tron_endpts[tid]

            # is the pole geometry coincident with *one* of the two end vertices?
            if not (
                pole_geom.intersects(QgsGeometry.fromPointXY(t_end_0).buffer(tol, 1)) or
                pole_geom.intersects(QgsGeometry.fromPointXY(t_end_1).buffer(tol, 1))
            ):
                continue                                    # touches mid-span → ignore

            # ------------ 4. now you KNOW it's a dangling endpoint ------------
            tip_leg = str(pf['TIP_LEG_JT']).strip().lower()
            cond_list = [
                str(tf['TIP_COND']).strip().lower()
            ]

            # --- 4.a “one BRANS BMPM/BMPT” sub-rule ----------
            br_hits = [
                self._brans.getFeature(bid)
                for bid in self._idx_brans.intersects(pole_geom.boundingBox())
                if self._brans.getFeature(bid).geometry().intersects(pole_geom)
            ]

            if len(br_hits) >= 1:
                tip_firi = str(br_hits[0]['TIP_FIRI_BR']).strip().lower()
                if tip_firi in {'bmpm', 'bmpt'} \
                and tip_leg not in ('t', 't/d') \
                and all(c not in allowed_cond for c in cond_list):
                    self._add_err_point(
                        pole_geom, "BRANS_FIRI_GRPM_JT", br_hits[0].id(),
                        f"STÂLP intersectează o singură BRANS_FIRI_GRPM_JT "
                        f"cu TIP_FIRI_BR = ‘{tip_firi.upper()}’.",
                        f"TIP_LEG_JT trebuie să fie ‘t’ sau ‘t/d’. Valoare actuală: {tip_leg}"
                    )
                    continue

    # ------------------------------------------------------------------
    #  RULE 6 – Întindere (ramificare) – ≥3 intersects & wrong TIP_LEG_JT
    # ------------------------------------------------------------------
    def _rule6_intindere(self):
        for feat in self._stalp.getFeatures():
            pt = feat.geometry().asPoint()
            # count how many tronson features touch this pole
            intersecting_trons = [tr for tr in self._nearest_lines(pt, self._idx_tronson, self._tronson)]
            if len(intersecting_trons) > 2:
                tip_leg = str(feat["TIP_LEG_JT"] or "").lower().strip()
                if tip_leg not in ("ic", "ic/d"):
                    self._add_err_point(feat.geometry(), "STALP_JT", feat.id(),
                                        "Întindere fără IC",
                                        f"STÂLP cu >2 TRONSON_JT dar TIP_LEG_JT ≠ ‘ic’/‘ic/d’. Valoare actuală: `{tip_leg.strip()}`")
                    
                    
    # ------------------------------------------------------------------
    #  RULE 7 – Rupere conductor via processing model
    # ------------------------------------------------------------------
    def _rule7_rupere_cond(self):
        """Runs the *1.2.RUPERE__CONDUCTOR* model and folds its two outputs straight
        into the existing error layers instead of adding separate ones.

        Assumptions
        -----------
        • The model outputs *conductorul_nu_e_rupt_la_cs*   (Point layer)
        •                 and *conductorul_nu_e_rupt* (Line layer).
        • Each output carries an **fid** attribute back‑linking to the source feature.
        • A point record signals a *conductor rupture at pole*;  a line record signals
          *conductor rupture on tronson* – both are considered errors.
        """
        
        params = {
            "linia_jt": self.linia_jt_val,
            "stalpi": self._stalp,
            "tronson": self._tronson,
            "conductorul_nu_e_rupt": QgsProcessing.TEMPORARY_OUTPUT,
            "conductorul_nu_e_rupt_la_cs": QgsProcessing.TEMPORARY_OUTPUT,
        }
        try:
            result = processing.run("model:1.2.RUPERE__CONDUCTOR", params)
        except Exception as e:
            QgsMessageLog.logMessage(f"Model RUPERE_CONDUCTOR failed: {e}", "VectorVerifier", level=Qgis.Critical)
            return

        # ---- Point output -> erori_stalp ----------------------------------
        pt_layer = result.get("conductorul_nu_e_rupt_la_cs")
        if isinstance(pt_layer, QgsVectorLayer):
            for f in pt_layer.getFeatures():
                fid_link = f["fid"] if "fid" in pt_layer.fields().names() else f.id()
                self._add_err_point(f.geometry(), "STALP_JT", fid_link,
                                    "Rupere conductor",
                                    "Conductorul nu e rupt/întrerupt pe stâlp")
        else:
            QgsMessageLog.logMessage("Output 'conductorul_nu_e_rupt' is not a vector layer", "VectorVerifier", level=Qgis.Warning)

        # ---- Line output -> erori_brans_tronson ---------------------------
        line_layer = result.get("conductorul_nu_e_rupt")
        if isinstance(line_layer, QgsVectorLayer):

            # Build a quick lookup on first use – O(1) fetch later
            use_attr = "fid" in self._tronson.fields().names()
            tronson_index = {
                (f["fid"] if use_attr else f.id()): f.geometry()
                for f in self._tronson.getFeatures()
            }

            for f in line_layer.getFeatures():
                fid_link = f["fid"] if "fid" in line_layer.fields().names() else f.id()

                # Grab the original geometry
                geom = tronson_index.get(fid_link)

                # fall back to a flattened copy if we can’t
                if geom is None:
                    g = f.geometry()
                    if g.isMultipart():                     # MultiLineString → first part
                        parts = g.asMultiPolyline()
                        geom = QgsGeometry.fromPolylineXY(parts[0])
                    else:
                        geom = g

                self._add_err_line(
                    geom,
                    "TRONSON_JT",
                    fid_link,
                    "Rupere conductor",
                    "Conductorul nu e rupt/întrerupt pe tronson",
                )
        else:
            QgsMessageLog.logMessage(
                "Output 'conductorul_nu_e_rupt' is not a vector layer",
                "VectorVerifier",
                level=Qgis.Warning,
            )


