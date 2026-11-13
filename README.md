# Smart JUTC Bus Tracking & Digital Fare Management System

A Streamlit-based Python prototype for commuter bus information, bus operations, digital fare collection, and revenue reconciliation. The existing business modules have been retained and connected to a browser-based interface.

## Main features

### Commuter
- Register and sign in; three failed sign-in attempts trigger a 15-minute lockout.
- Browse active routes and schedules, including bus number, route ID, departure and arrival times, and fare.
- Select a bus to see its demonstration position and tracking status on a map.
- Manage main and virtual bus-card balances, with fares deducted from the virtual balance.
- Review fare payments, top-ups and receipts linked to the signed-in account.

### Administrator
- View bus, route, driver-count and commuter information.
- Assign a bus, route and driver; start and end bus service.
- Record GPS coordinates and service status.
- Submit radio-delay reports.
- Add routes, submit daily collections, reconcile revenue, and view reports.

### Main Administrator
- Exactly one Main Administrator is created through deployment environment secrets.
- View registered accounts.
- Grant `ADMIN` to an existing commuter or revoke an ordinary administrator's privileges by changing the role to `COMMUTER`.
- View the role-change audit log.
- The Main Administrator role cannot be assigned through the dashboard or public registration.

## Important prototype limitations

- GPS coordinates are entered manually. Live vehicle tracking requires approved GPS/telematics hardware and an integration.
- Radio delay reporting is represented by a database workflow; it is not connected to a physical radio network.
- Cash is recorded after staff collect it. The application does not physically collect cash.
- Bus-card balances and credit/debit top-ups are local demonstration records, not a live fare-card or payment-provider integration. Card details are not collected.
- Sample routes, fares, buses and schedules are inserted for demonstration. Tracking statuses and map positions are simulated demonstration data, not live GPS readings. Replace them with approved operational data before deployment.
- This is a coursework/demo prototype, not a production-ready transport or payment platform. Add deployment-grade security review, HTTPS, backups, monitoring, stronger audit controls and approved integrations before real-world use.
- **Board Bus is not included.**

## Requirements

- Python 3.10 or newer
- Visual Studio Code
- Packages listed in `requirements.txt`

## Run locally in VS Code

1. Open the `smart_jutc_bus_system` folder in VS Code.
2. Open **Terminal → New Terminal**.
3. Create and activate a virtual environment:

   Windows PowerShell:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   Windows Command Prompt:
   ```bat
   python -m venv .venv
   .venv\Scripts\activate.bat
   ```

4. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
5. Start the application:
   ```bash
   streamlit run app.py
   ```
6. Streamlit will display a local address, normally `http://localhost:8501`, which opens in your browser.

The SQLite database is created automatically at `data/jutc_system.db`.

## Configure the Main Administrator

Do not create a Main Administrator through the registration page. Configure these environment variables before the first app launch:

- `JUTC_MAIN_ADMIN_USERNAME`
- `JUTC_MAIN_ADMIN_EMAIL`
- `JUTC_MAIN_ADMIN_PASSWORD`

PowerShell example for the current terminal only:

```powershell
$env:JUTC_MAIN_ADMIN_USERNAME="mainadmin"
$env:JUTC_MAIN_ADMIN_EMAIL="admin@example.com"
$env:JUTC_MAIN_ADMIN_PASSWORD="CHANGE-THIS-TO-A-LONG-UNIQUE-PASSWORD"
streamlit run app.py
```

Use your own values. Do not put real credentials in source code, `.env.example`, README files, or GitHub. For a hosted deployment, use the host's secrets/environment-variable settings. The bootstrap creates a Main Administrator only if no Main Administrator already exists. Keep the credentials private.

## Project structure

```text
smart_jutc_bus_system/
├── app.py
├── main.py
├── requirements.txt
├── README.md
├── .gitignore
├── bus_system/
│   ├── __init__.py
│   ├── authentication.py
│   ├── permissions.py
│   ├── user_management.py
│   ├── database.py
│   ├── utils.py
│   ├── route_scheduling.py
│   ├── bus_operations.py
│   ├── fare_management.py
│   ├── revenue.py
│   └── cli.py                 # Legacy command-line interface; app uses Streamlit
├── tests/
│   ├── __init__.py
│   └── test_core.py
└── data/                      # Local database; excluded from Git
```

## Run tests

```bash
python -m unittest discover -s tests -v
```

The included tests cover core fare and GPS validation. They are not a complete security, integration, or production acceptance test suite.

## Git and GitHub

```bash
git init
git add .
git commit -m "Set up Smart JUTC Streamlit application"
```

Create an empty repository on GitHub, then connect it using the repository URL GitHub provides:

```bash
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

The `.gitignore` excludes the local database, virtual environment, caches and local secret files. Never commit real account credentials or production data.
