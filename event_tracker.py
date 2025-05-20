from qgis.core import QgsProject # type: ignore
from PyQt5.QtCore import QObject, QTimer #type: ignore
from .api_client import send_event
from .config import LAYERS, NULL_VALUES, IDLE_SECONDS

class EditTracker(QObject):
    def __init__(self, iface, user_name):
        super().__init__()
        self.iface = iface
        self.user = user_name
        self.checked_in = False
        self.is_idle = False
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(IDLE_SECONDS * 1000)
        self.idle_timer.timeout.connect(self._on_idle_timeout)
        self.idle_timer.start()

        self._connect_layers()
        QgsProject.instance().layersAdded.connect(self._on_layers_added)
        self.iface.projectRead.connect(self._on_project_opened)
        self.iface.mapCanvas().extentsChanged.connect(self._reset_idle_timer)
        send_event(user=self.user, action="session_start")

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
            layer.editingStarted.connect(self.on_edit_start)
            layer.editingStopped.connect(self.on_edit_stop)

    # ----------------------------------------------------------------------
    # Each slot uses self.sender() to know WHICH layer fired the signal ------
    def on_add(self, fid):
        lyr = self.sender()                         # QgsVectorLayer
        self._check_in()
        self._reset_idle_timer()
        send_event(
            user = self.user,
            layer  = lyr.name(),                   # ← STALP_JT etc.
            action = "add",
            fid    = fid
        )

    def on_delete(self, fid):
        lyr = self.sender()
        self._check_in()
        self._reset_idle_timer()
        send_event(
            user = self.user,
            layer  = lyr.name(),
            action = "delete",
            fid    = fid
        )

    def on_attr(self, fid, idx, val):
        lyr        = self.sender()
        field_name = lyr.fields()[idx].name()       # turn index -> name
        self._check_in()
        self._reset_idle_timer()

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
        self._check_in()
        self._reset_idle_timer()

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

    # ----------------------------------------------------------------------
    def on_edit_start(self):
        lyr = self.sender()
        self._check_in()
        self._reset_idle_timer()
        send_event(
            user=self.user,
            layer=lyr.name(),
            action="edit_start",
        )

    def on_edit_stop(self):
        lyr = self.sender()
        send_event(
            user=self.user,
            layer=lyr.name(),
            action="edit_stop",
        )

    def _on_layers_added(self, layers):
        for layer in layers:
            if layer.name() in LAYERS:
                layer.featureAdded.connect(self.on_add)
                layer.featureDeleted.connect(self.on_delete)
                layer.attributeValueChanged.connect(self.on_attr)
                layer.geometryChanged.connect(self.on_geom)
                layer.editingStarted.connect(self.on_edit_start)
                layer.editingStopped.connect(self.on_edit_stop)

    def _on_project_opened(self):
        if self.checked_in:
            send_event(user=self.user, action="check_out")
            self.checked_in = False
        send_event(
            user=self.user,
            action="project_open",
            value=QgsProject.instance().fileName(),
        )

    def _on_idle_timeout(self):
        if not self.is_idle:
            self.is_idle = True
            send_event(user=self.user, action="idle_start")

    def _reset_idle_timer(self, *args):
        if self.is_idle:
            send_event(user=self.user, action="idle_end")
            self.is_idle = False
        self.idle_timer.start()

    def _check_in(self):
        if not self.checked_in:
            send_event(user=self.user, action="check_in")
            self.checked_in = True

    def finalize(self):
        if self.checked_in:
            send_event(user=self.user, action="check_out")
        send_event(user=self.user, action="session_end")
