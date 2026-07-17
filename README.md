# Composite Bridge Data Portal

This folder contains the Streamlit version of the Composite Bridge Data Portal.
It is organized as six Python scripts so the project stays simple while making
future pages easy to add.

## Portal pages

- **Home** — downloads the latest private S3 files and loads them into DuckDB.
- **Graphing** — reproduces the main GraphixCB filtering, Plotly, frequency,
  time-range, box-selection, and statistics features.
- **Export Center** — exports any selected variables as one CSV or one Excel file.
- **About** — explains the research project, datasets, and portal workflow.

## Project structure

```text
DataPortal/
├── app.py
├── data.py
├── pages/
│   ├── home.py
│   ├── graphing.py
│   ├── export_center.py
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
  Minutes, and Custom Range.
- Minimum point frequency is applied in DuckDB before results enter memory.
- Graph lines break when readings are separated by more than ten minutes.
- The graph supports zoom, pan, hover, point selection, box selection, and
  lasso selection.
- Selection statistics stay hidden until graph points are selected.
- For browser stability, one graph is limited to 750,000 selected points.

## Export notes

- Every export is one file.
- Variables from different datasets are combined by exact timestamp.
- CSV remains available for outputs larger than an Excel worksheet.
- Excel is disabled when the combined output exceeds 1,048,575 data rows,
  reserving one worksheet row for the column headings.
- Excel files contain one worksheet named `Bridge Data`.
- Prepared files are temporary and are cleaned from the server after two hours.

## Changing colors and fonts

Open `app.py` and find the clearly labeled **APPEARANCE SETTINGS** section near
the top. The portal background, sidebar, buttons, graph, grid, text, title,
font, sizes, and logo width can be changed there without editing page logic.

## Adding another page later

1. Add one new Python file inside `pages/`.
2. Add one matching `st.Page(...)` entry to the **MULTIPAGE NAVIGATION** section
   of `app.py`.

No changes to the other page files are required unless the new page needs new
shared data functions.
