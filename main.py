"""Initialise the database and launch the Streamlit application."""
from bus_system.database import initialize_database

if __name__ == "__main__":
    initialize_database()
    print("Database initialised. Start the web app with: streamlit run app.py")
