from qgis.core import QgsProject
from PyQt5.QtCore import QObject
from .api_client import send_event
from .config import LAYERS, NULL_VALUES          

class EditTracker(QObject):
    def __init__(self, iface, user_name):
        super().__init__()
        self.iface = iface
        self.user = user_name
        self._connect_layers()

    # ----------------------------------------------------------------------
    def _connect_layers(self):
        for name in LAYERS:
            layer_list = QgsProject.instance().mapLayersByName(name)
            if not layer_list:
                self.iface.messageBar().pushWarning(
                    "Digitizer", f"Layer “{name}” not found – skipping")
                continue

            layer = layer_list[0]                   # the QgsVectorLayer
            # connect signals → slots
            layer.featureAdded.connect(self.on_add)
            layer.featureDeleted.connect(self.on_delete)
            layer.attributeValueChanged.connect(self.on_attr)
            layer.geometryChanged.connect(self.on_geom)

    # ----------------------------------------------------------------------
    # Each slot uses self.sender() to know WHICH layer fired the signal ------
    def on_add(self, fid):
        lyr = self.sender()                         # QgsVectorLayer
        send_event(
            user = self.user,
            layer  = lyr.name(),                   # ← STALP_JT etc.
            action = "add",
            fid    = fid
        )

    def on_delete(self, fid):
        lyr = self.sender()
        send_event(
            user = self.user,
            layer  = lyr.name(),
            action = "delete",
            fid    = fid
        )

    def on_attr(self, fid, idx, val):
        lyr        = self.sender()
        field_name = lyr.fields()[idx].name()       # turn index -> name

        # example validation – forbid NULL in COD
        if field_name == "COD" and val in NULL_VALUES:
            self.iface.messageBar().pushWarning(
                "Rule", f"{field_name} cannot be NULL – change rejected")
            return

        send_event(
            user = self.user,
            layer  = lyr.name(),
            action = "attr",
            fid    = fid,
            field  = field_name,
            value  = val
        )

    def on_geom(self, fid, geom):
        lyr = self.sender()

        # simple geometry validation
        if not geom.isSimple():
            self.iface.messageBar().pushCritical(
                "Rule", "Self-intersecting geometry – change rejected")
            return

        send_event(
            user = self.user,
            layer  = lyr.name(),
            action = "geom",
            fid    = fid,
            wkt    = geom.asWkt()
        )
