# DesenAssist

**DesenAssist** is a QGIS 3 plugin built for a private company internal team to accelerate digitization and quality‑control of low‑voltage underground utility poles and related network features.
While the code is public‑facing, it assumes our layer names, field schema and corporate‑wide conventions, so mileage outside the company may vary.

---

## Why I wrote it
Manual QA on thousands of poles is slow and error‑prone. DesenAssist sits in its own toolbar, automating the most repetitive steps—field completion, validation, layer slicing and quick Excel exports, so technicians can focus on genuine edge‑cases.

---

## Key actions (toolbar buttons)

| Icon | Action | What it does |
|------|--------|--------------|
| 📂 | **Fisier Destinatie** | Set the working directory for all generated files. |
| 🖼️ | **Încarcă fișiere .ui** | Loads the customised Qt Designer forms shipped with the project. |
| 🔀 | **Separare posturi după ID_BDI / selecție** | Splits the pole layer into separate outputs by `ID_BDI` or by the current selection. |
| ✂️ | **Ajustare bransamente la 1 m** | Cuts service‑line segments (`BRANS_FIRI_GRPM_JT`) to a fixed 1 m length from the pole. |
| 🧩 | **Completare câmpuri** | Auto‑populates mandatory fields using predefined rules for every target layer. |
| 🔢 | **Verificare numerotare stâlpi** | Flags duplicate or out‑of‑sequence pole numbers. |
| 🛣️ | **Verificare denumire străzi** | Cross‑checks street names in `STALP_JT` and `BRANS_FIRI_GRPM_JT` against the corporate road database. |
| ↔️ | **Corespondență LINIA_JT – TRONSON_JT** | Confirms each service connection points to an existing LV line segment. |
| 📑 | **Verificare coloane** | Ensures all mandatory columns exist and are of the correct type. |
| ⚡ | **Verificare circuit greșit** | Detects poles assigned to the wrong electrical circuit. |
| 📊 | **Verificare străzi & Excel** | Generates a ready‑to‑send Excel report for street‑name mismatches. |
| 📏 | **Lungime TRONSON_JT** | One‑click length calculation the segments of layer "TRONSON_XML", overlapped segments only count twice. After the button is clicked one, it keeps calculating the length automatically. |

---

## Installation

1. Clone or download this repository.  
2. Copy the folder to your local QGIS plugin directory:  
   * **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins`  
   * **Linux/macOS:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins`
3. Restart QGIS and activate **DesenAssist** via *Plugins › Manage and Install Plugins*.

> **Prerequisites**  
> QGIS 3.22 LTS or newer. External dependencies: xlsxwriter

---

## Quick start

1. Load your standard project template (the plugin expects the usual layer names with the designated columns).
2. Click **Fisier Destinatie** and pick the output folder.
3. Use **Completare câmpuri** to auto‑fill mandatory attributes.
4. Run the relevant validation actions to clean up errors.
5. Export reports if needed. Done.

---

## Known limitations

* Hard‑coded field names, layer names and value domains.  
* Built for Romanian LV datasets; international schemas will need tweaks.  
* UI only in RO at the moment.

## Telemetry

DesenAssist now emits additional events to the local backend. The tracker records
button clicks, project changes and idle time. Placeholder metrics for presence
and productivity will be expanded in future releases.

---

## Support
 
External users (at your own risk): open an issue on GitHub and I'll answer when I can.
