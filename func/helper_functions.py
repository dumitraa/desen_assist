import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from qgis.core import QgsVectorLayer, QgsProject, QgsMessageLog, Qgis # type: ignore


class HelperBase:
    def __init__(self):
        super().__init__()
        self.processor = None
        
    # Retrieve layers by name from the QGIS project
    def get_layers(self):
        '''
        Get layers by name from the QGIS project and add them to self.layers
        '''
        layers = {}
        layer_names = ['STALP_JT', 'TRONSON_JT', 'BRANS_FIRI_GRPM_JT', 'FB pe C LES', 'FIRIDA_RETEA_JT', 'GRID_GEIOD', 'PTCZ_PTAB', 'TRONSON_XML_', 'TRONSON_ARANJARE', 'poze', 'FIRIDA_XML_', 'BRANSAMENT_XML_', 'GRUP_MASURA_XML_', 'STALP_XML_', 'DESCHIDERI_XML_', 'TRONSON_predare_xml', 'LINIE_MACHETA', 'STALPI_MACHETA', 'TRONSON_MACHETA', 'FIRIDA MACHETA', 'GRUP MASURA MACHETA', 'DESCHIDERI MACHETA', 'BRANSAMENTE MACHETA', 'LINIE_JT']
        
        # Get all layers in the current QGIS project (keep the layer objects)
        try:
            qgis_layers = QgsProject.instance().mapLayers().values()
            if not qgis_layers:
                raise ValueError("No layers found in the project.")
        except Exception as e:
            QgsMessageLog.logMessage(f"Error getting layers: {e}", "DesenAssist", level=Qgis.Critical)
            return layers

        # Iterate through the actual layer objects
        for layer_name in layer_names:
            layer = next((l for l in qgis_layers if l.name() == layer_name), None)
            layers[layer_name] = layer  # Add the layer if found, else None

        return layers


    def add_layer_to_project(self, layer_path):
        try:
            # Get the name of the layer without the file extension and the full path
            layer_name = os.path.splitext(os.path.basename(layer_path))[0]
            
            # Load the merged layer from the output path
            merged_layer = QgsVectorLayer(layer_path, layer_name, 'ogr')
            
            # Check if the layer is valid
            if not merged_layer.isValid():
                QgsMessageLog.logMessage(f"Invalid layer: {layer_path}", "DesenAssist", level=Qgis.Critical)
                return
            
            # Add the layer to the project with the proper name
            QgsProject.instance().addMapLayer(merged_layer)
            
        except Exception as e:
            QgsMessageLog.logMessage(f"Error adding layer to project: {e}", "DesenAssist", level=Qgis.Critical)
            
            
    def run_algorithm(self, algorithm, params, context, feedback, output_key):
        try:
            # Step 1: Run the algorithm
            results = algorithm.processAlgorithm(params, context, feedback)
            
            # Step 2: Retrieve the desired output path(s)
            output_path = results.get(output_key)
            
            if not output_path:
                QgsMessageLog.logMessage(f"Output not found for key: {output_key}", "DesenAssist", level=Qgis.Critical)
                return False

            # Step 3: Add the output layer to the project
            self.add_layer_to_project(output_path)
            return True

        except Exception as e:
            QgsMessageLog.logMessage(f"Error processing and adding output: {e}", "DesenAssist", level=Qgis.Critical)
            return False

# MARK: PARSERS
    def save_xml(self, xml_name, name, xml_file):
        root = ET.Element(xml_name) 

        for linie in self.linii:
            linie_element = ET.SubElement(root, name)
            for attr, value in linie.__dict__.items():
                child = ET.SubElement(linie_element, attr.upper())
                child.text = str(value) if value is not None else ""

        rough_string = ET.tostring(root, 'utf-8-sig')

        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="    ")

        with open(xml_file, 'w', encoding='utf-8-sig') as f:
            f.write(pretty_xml)
        
        
class SHPProcessor:
    '''
    Class to process the SHP layers, validate them and load them into QGIS
    '''
    def __init__(self, layers):
        '''
        Constructor for the SHPProcessor class
        :param layers: A dictionary with layer names and their respective QgsVectorLayer objects
        :param output_xlsx: The name of the output Excel file
        '''
        self.layers = layers
        self.parsers = []
        self.invalid_elements = []
        self.load_layers()
        
        
        

