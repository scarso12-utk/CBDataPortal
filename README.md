# Composite Bridge Data Portal

This repository contains the Streamlit version of the Composite Bridge Data
Portal. The application securely loads the latest bridge sensor data from
Amazon S3 into DuckDB, then provides graphing, export, and analytical tools
through a password-protected multipage interface.

## Portal pages

- **Home** — checks Amazon S3 for updated files, downloads changed objects,
  builds or reuses the local DuckDB database, and displays dataset status.
- **Graphing** — creates interactive Plotly graphs with variable selection,
  time-range presets, point-frequency thinning, gap handling, zoom, pan,
  box/lasso selection, and selection statistics.
- **Export Center** — combines selected variables by exact timestamp and exports
  the chosen time range as one CSV or Excel file.
- **Analytics** — provides specialized research tools:
  - **Vehicle Events Identifier** matches acceleration bursts with later
    increases in the environmental `Count` variable.
  - **FFT / Frequency Analysis** has its workspace and documentation in place;
    its data-selection and frequency-spectrum calculations are planned.
- **About** — explains the bridge, instrumentation, datasets, architecture,
  limitations, and intended research use.

## Project structure

```text
CBDataPortal/
├── app.py
├── data.py
├── analytics_tools/
│   ├── __init__.py
│   ├── crash_events.py
│   └── frequency.py
├── pages/
│   ├── home.py
│   ├── graphing.py
│   ├── export_center.py
│   ├── analytics.py
│   └── about.py
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Data source

The portal retrieves these private objects from Amazon S3:

```text
s3://composite-bridge-data-568788909451-us-east-1-an/logo.png
s3://composite-bridge-data-568788909451-us-east-1-an/accell.csv
s3://composite-bridge-data-568788909451-us-east-1-an/deflect.csv
s3://composite-bridge-data-568788909451-us-east-1-an/envir.csv
```

The default AWS region is `us-east-1`. The bucket, region, and optional S3
prefix are read from Streamlit Secrets, so the app can be deployed without
putting AWS details directly into the code.

The CSV files should not be added to GitHub. The Home page downloads them from
S3 when **Load Data** is pressed.

## 1. Install Python

Install Python 3.11, 3.12, or 3.13. Python 3.12 is a conservative choice for
local development and deployment.

## 2. Open the folder

Open the `DataPortal` folder in Visual Studio Code or a terminal.

## 3. Create a virtual environment

### macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run this once in that terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 4. Configure secrets

For Streamlit Community Cloud, paste this TOML into the app's **Advanced
settings** Secrets box:

```toml
[portal]
password = "CHOOSE_A_SHARED_PORTAL_PASSWORD"

[aws]
access_key_id = "YOUR_AWS_ACCESS_KEY_ID"
secret_access_key = "YOUR_AWS_SECRET_ACCESS_KEY"
region = "us-east-1"
bucket_name = "composite-bridge-data-568788909451-us-east-1-an"
prefix = ""
```

Do not upload a real `secrets.toml` file to GitHub. The included `.gitignore`
blocks it by default.

## 5. Run locally

### macOS

```bash
streamlit run app.py
```

### Windows PowerShell

```powershell
streamlit run app.py
```

Streamlit normally opens the portal automatically. If needed, visit:

```text
http://localhost:8501
```

Enter the shared portal password, open Home, and press **Load Data**.

## AWS permission requirement

The access key should belong to a dedicated IAM identity with read-only access
to the four required objects. A minimal resource list is:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": [
        "arn:aws:s3:::composite-bridge-data-568788909451-us-east-1-an/logo.png",
        "arn:aws:s3:::composite-bridge-data-568788909451-us-east-1-an/accell.csv",
        "arn:aws:s3:::composite-bridge-data-568788909451-us-east-1-an/deflect.csv",
        "arn:aws:s3:::composite-bridge-data-568788909451-us-east-1-an/envir.csv"
      ]
    }
  ]
}
```

Do not use the AWS root account's access keys.

## Deploy to Streamlit Community Cloud

1. Create a GitHub repository.
2. Upload the contents of `DataPortal` to that repository.
3. Confirm that `.venv`, CSV files, DuckDB files, and `secrets.toml` are absent.
4. In Streamlit Community Cloud, choose **Create app**.
5. Select the GitHub repository, branch, and `app.py` entrypoint.
6. Open **Advanced settings** and paste the TOML secrets from this README into
   the Secrets field.
7. Deploy the application.

To allow anyone with the shared password to reach the password screen, set the
Streamlit app itself to public. The application does not expose navigation or
data until the shared password is entered.

## How loading works

- The portal checks all four S3 objects whenever **Load Data** is pressed.
- Files are downloaded only when their S3 version has changed or the local
  temporary cache is missing.
- DuckDB is rebuilt when one of the three CSV files changes.
- The database is shared by sessions running on the same Streamlit server.
- Community Cloud storage is temporary, so data must be loaded again after a
  full app restart or cache reset.

## Graphing notes

- Time controls use `America/New_York`.
- Presets include Entire Dataset, Last Week, Last Day, Last Hour, Last 10
  Minutes, a saved range from the Export Center, and Custom Range.
- The most recently generated graph range remains available while the user
  moves between pages.
- Minimum point frequency is applied in DuckDB before results enter memory.
- Graph lines break when readings are separated by more than ten minutes.
- The graph supports zoom, pan, hover, point selection, box selection, and
  lasso selection.
- Selection statistics stay hidden until graph points are selected.
- For browser stability, one graph is limited to 750,000 selected points.

## Export notes

- Every export is one file.
- Variables from different datasets are combined by exact timestamp.
- Presets include the saved time range from the Graphing page, and the latest
  calculated export range remains available while the user changes pages.
- The portal calculates the exact combined row count before creating a file.
- CSV remains available for outputs larger than an Excel worksheet.
- Excel is disabled when the combined output exceeds 1,048,575 data rows,
  reserving one worksheet row for the column headings.
- Excel files contain one worksheet named `Bridge Data`.
- Prepared files are temporary and are cleaned from the server after two hours.

## Analytics notes

### Vehicle Events Identifier

- Requires both acceleration and environmental data over an overlapping time range.
- Groups nearby acceleration readings into bursts.
- Treats positive changes in `Count` as vehicle detections and ignores counter
  decreases as resets.
- Confirms a burst only when a later Count increase occurs within the selected
  delay window. The default maximum delay is 45 seconds.
- Excludes ambiguous windows containing more acceleration bursts than counted
  vehicles instead of guessing.
- Displays summary metrics and allows confirmed events to be downloaded as CSV.
- Results are high-confidence analytical estimates, not absolute physical proof.

### FFT / Frequency Analysis

The FFT workspace currently explains the planned analysis and checks whether
bridge data is loaded. Axis selection, time-window controls, FFT calculations,
frequency-spectrum graphs, dominant-frequency detection, comparisons, and
result exports are planned for a future update.

## Changing colors and fonts

Open `app.py` and find the clearly labeled **APPEARANCE SETTINGS** section near
the top. The portal background, sidebar, buttons, graph, grid, text, title,
font, sizes, and logo width can be changed there without editing page logic.

## Adding another page later

1. Add one new Python file inside `pages/`.
2. Add one matching `st.Page(...)` entry in `app.py`.
3. Add the page object to the authenticated `st.navigation(...)` list.

No changes to the other page files are required unless the new page needs shared
data functions from `data.py` or a specialized module in `analytics_tools/`.
