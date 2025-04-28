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
)
from qgis.PyQt.QtCore import QVariant # type: ignore

from .helper_functions import HelperBase


class VectorVerifier:
    """Encapsulates the logic for validating STALP_JT, BRANS_FIRI_GRPM_JT and TRONSON_JT layers.

    Creates two in‑memory layers containing the geometry/attribute errors it detects:
        • erori_stalp  – point layer (errors concerning STALP_JT)
        • erori_brans_tronson – line layer (errors concerning BRANS_FIRI_GRPM_JT or TRONSON_JT)
    Both layers receive four string/int fields:  NUME_LAYER, FID, TIP_EROARE, DETALII.
    At the end they are added to the current group "DE_VERIFICAT" in the QGIS project.
    """

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

        # Perform the five groups of checks
        self._rule1_snapping()
        self._rule2_tip_cir_br()
        self._rule3_tip_cir_jt()
        self._rule4_terminal_br()
        self._rule5_terminal_tronson()

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
            if snapped_to_terminal_br and str(feat["TIP_LEG_JT"]).lower() in ["t", "t/d"] and self._contains_letters(feat["DENUM"]):
                self._add_err_point(feat.geometry(), "STALP_JT", feat.id(),
                                    "Terminal BR greșit",
                                    "STÂLP terminal pe BRANS cu litere în DENUM și TIP_LEG_JT = t / t/d")

    @staticmethod
    def _contains_letters(val) -> bool:
        return any(ch.isalpha() for ch in str(val))

    # ------------------------------------------------------------------
    #  RULE 5 – dangling TRONSON endpoints need ‘t’ or ‘t/d’ on STALP
    # ------------------------------------------------------------------
    def _rule5_terminal_tronson(self):
        allowed_cond = {
            "tyir 16al + 25al",          # normalise to lower case once
            "tyir 3x25al + 16al"
        }

        # ---------- 1. catalogue every endpoint and its conductor type -----------
        end_pts        = {}        # (x,y) ➜ count
        end_cond_types = {}        # (x,y) ➜ list of TIP_COND strings

        for feat in self._tronson.getFeatures():
            geom = feat.geometry()
            c0   = QgsPointXY(geom.constGet().pointN(0))
            c1   = QgsPointXY(geom.constGet().pointN(geom.constGet().numPoints() - 1))

            for p in (c0, c1):
                key = (round(p.x(), 6), round(p.y(), 6))
                end_pts[key] = end_pts.get(key, 0) + 1
                end_cond_types.setdefault(key, []).append(
                    str(feat["TIP_COND"]).strip().lower()
                )

        dangling_coords = {k for k, v in end_pts.items() if v == 1}

        # ------------- 2. validate each dangling coordinate ----------------------
        for coord in dangling_coords:
            pt_geom = QgsGeometry.fromPointXY(QgsPointXY(*coord))

            nearest_ids = self._idx_stalp.nearestNeighbor(QgsPointXY(*coord), 3)
            if not nearest_ids:
                self._add_err_line(
                    pt_geom, "TRONSON_JT", -1,
                    "Sfârșit tronson fără STÂLP",
                    "Capăt de TRONSON fără STALP_JT corespunzător"
                )
                continue

            fid         = nearest_ids[0]
            stalp_feat  = self._stalp.getFeature(fid)

            if pt_geom.distance(stalp_feat.geometry()) > self._tol:
                self._add_err_line(
                    pt_geom, "TRONSON_JT", -1,
                    "Sfârșit tronson fără STÂLP",
                    "Capăt de TRONSON fără STALP_JT corespunzător"
                )
                continue

            tip_leg   = str(stalp_feat["TIP_LEG_JT"]).strip().lower()
            cond_list = end_cond_types.get(coord, [])

            # ---- 3. raise only if TIP_LEG is bad *and* no conductor is allowed --
            if tip_leg not in ("t", "t/d") and all(c not in allowed_cond for c in cond_list):
                self._add_err_point(
                    stalp_feat.geometry(), "STALP_JT", stalp_feat.id(),
                    "STÂLP final fără TIP_LEG adecvat",
                    f"La capăt de TRONSON, TIP_LEG_JT trebuie să fie ‘t’ sau ‘t/d’. "
                    f"Valoare actuală: `{tip_leg}`"
                )

