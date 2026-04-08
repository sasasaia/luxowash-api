import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
import pymssql
from PythonSimpleFunctions import bake

app = Flask(__name__)
CORS(app)

def get_connection():
    return pymssql.connect(
        os.environ.get("DB_SERVER"),
        os.environ.get("DB_USER"),
        os.environ.get("DB_PASS"),
        os.environ.get("DB_NAME")
    )

def log_activity(cursor, message):
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute("INSERT INTO ActivityList (ActivityMessage, ActivityDate) VALUES (%s, %s)", (message, now))
    except:
        # Fallback if ActivityDate column doesn't exist yet
        cursor.execute("INSERT INTO ActivityList (ActivityMessage) VALUES (%s)", (message,))

@app.route("/")
def home():
    return jsonify(bake("luxowash-api"))

@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.json
        username = data.get("username")
        password = data.get("password")

        conn = get_connection()
        cursor = conn.cursor(as_dict=True)

        # Check Admin
        cursor.execute("SELECT * FROM AdminList WHERE Username = %s AND Password = %s", (username, password))
        admin = cursor.fetchone()
        if admin:
            log_activity(cursor, f"Admin {username} logged in.")
            conn.commit()
            conn.close()
            return jsonify({"role": "admin", "username": username})

        # Check User
        cursor.execute("SELECT * FROM UserList WHERE Username = %s AND Password = %s", (username, password))
        user = cursor.fetchone()
        if user:
            # Record login time if needed, but the request says "add a time in schedule for user accounts according to log in"
            # This might mean recording the actual login time for the day.
            now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE UserList SET LastLogin = %s WHERE Username = %s", (now, username))
            log_activity(cursor, f"User {username} logged in.")
            conn.commit()
            conn.close()
            return jsonify({"role": "user", "username": username})

        conn.close()
        return jsonify(bake("Invalid credentials")), 401
    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- EMPLOYEES ---
@app.route("/api/employees", methods=["GET", "POST", "PUT"])
def employees():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)

        if request.method == "GET":
            cursor.execute("SELECT * FROM EmployeeList")
            rows = cursor.fetchall()
            conn.close()
            return jsonify(rows)

        elif request.method == "POST":
            data = request.json
            emp_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO EmployeeList (EmployeeId, LastName, FirstName, MiddleName, MobileNumber, EmployeeAddress) VALUES (%s, %s, %s, %s, %s, %s)",
                (emp_id, data.get("LastName"), data.get("FirstName"), data.get("MiddleName"), data.get("MobileNumber"), data.get("EmployeeAddress"))
            )
            log_activity(cursor, f"Added employee {data.get('FirstName')} {data.get('LastName')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Added successfully"))

        elif request.method == "PUT":
            data = request.json
            cursor.execute(
                "UPDATE EmployeeList SET LastName=%s, FirstName=%s, MiddleName=%s, MobileNumber=%s, EmployeeAddress=%s WHERE EmployeeId=%s",
                (data.get("LastName"), data.get("FirstName"), data.get("MiddleName"), data.get("MobileNumber"), data.get("EmployeeAddress"), data.get("EmployeeId"))
            )
            log_activity(cursor, f"Updated employee {data.get('EmployeeId')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Updated successfully"))

    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/employees/time", methods=["POST"])
def employee_time():
    try:
        data = request.json
        emp_id = data.get("EmployeeId")
        action = data.get("action") # "in" or "out"
        now = datetime.now(timezone(timedelta(hours=8)))
        time_str = now.strftime("%I:%M:%S %p")
        date_str = now.strftime("%Y-%m-%d %I:%M:%S %p")
        today_prefix = now.strftime("%Y-%m-%d") + "%"

        conn = get_connection()
        cursor = conn.cursor(as_dict=True)

        if action == "in":
            # Check if already timed in today (any record, even if timed out)
            cursor.execute(
                "SELECT * FROM EmployeeTimeList WHERE EmployeeId = %s AND LEFT(DateCreated, 10) = %s",
                (emp_id, now.strftime("%Y-%m-%d"))
            )
            if cursor.fetchone():
                conn.close()
                return jsonify(bake("Employee has already timed in today.")), 400

            cursor.execute(
                "INSERT INTO EmployeeTimeList (EmployeeId, TimeIn, DateCreated) VALUES (%s, %s, %s)",
                (emp_id, time_str, date_str)
            )
            log_activity(cursor, f"Employee {emp_id} timed in.")
        elif action == "out":
            # Check if timed in today
            cursor.execute(
                "SELECT * FROM EmployeeTimeList WHERE EmployeeId = %s AND LEFT(DateCreated, 10) = %s AND TimeOut IS NULL",
                (emp_id, now.strftime("%Y-%m-%d"))
            )
            if not cursor.fetchone():
                conn.close()
                return jsonify(bake("Employee is not timed in or already timed out.")), 400

            # Update the latest record without a TimeOut for today
            cursor.execute(
                "UPDATE EmployeeTimeList SET TimeOut = %s WHERE EmployeeId = %s AND LEFT(DateCreated, 10) = %s AND TimeOut IS NULL",
                (time_str, emp_id, now.strftime("%Y-%m-%d"))
            )
            log_activity(cursor, f"Employee {emp_id} timed out.")

        conn.commit()
        conn.close()
        return jsonify(bake("Time recorded"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/employees/time/active", methods=["GET"])
def active_employees():
    try:
        now_manila = datetime.now(timezone(timedelta(hours=8)))
        today_prefix = now_manila.strftime("%Y-%m-%d") + "%"
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT e.* FROM EmployeeList e
            JOIN EmployeeTimeList t ON e.EmployeeId = t.EmployeeId
            WHERE LEFT(t.DateCreated, 10) = %s AND t.TimeOut IS NULL
        """, (now_manila.strftime("%Y-%m-%d"),))
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/employees/time/logs", methods=["GET"])
def employee_time_logs():
    try:
        date_filter = request.args.get("date") # YYYY-MM-DD
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        query = """
            SELECT t.*, e.FirstName, e.LastName 
            FROM EmployeeTimeList t
            JOIN EmployeeList e ON t.EmployeeId = e.EmployeeId
        """
        if date_filter:
            query += " WHERE LEFT(t.DateCreated, 10) = %s"
            cursor.execute(query + " ORDER BY t.DateCreated DESC", (date_filter,))
        else:
            cursor.execute(query + " ORDER BY t.DateCreated DESC")
            
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        
        if request.method == "GET":
            cursor.execute("SELECT * FROM SettingsList")
            rows = cursor.fetchall()
            # Convert to dict for easier use
            settings_dict = {row['SettingKey']: row['SettingValue'] for row in rows}
            conn.close()
            return jsonify(settings_dict)
            
        elif request.method == "POST":
            data = request.json # Expecting {key: value}
            for key, value in data.items():
                # Check if exists
                cursor.execute("SELECT * FROM SettingsList WHERE SettingKey = %s", (key,))
                if cursor.fetchone():
                    cursor.execute("UPDATE SettingsList SET SettingValue = %s WHERE SettingKey = %s", (str(value), key))
                else:
                    cursor.execute("INSERT INTO SettingsList (SettingKey, SettingValue) VALUES (%s, %s)", (key, str(value)))
            
            conn.commit()
            conn.close()
            return jsonify(bake("Settings updated"))
    except Exception as e:
        # If table doesn't exist, try to create it (simple migration)
        try:
            cursor.execute("CREATE TABLE SettingsList (SettingKey NVARCHAR(255) PRIMARY KEY, SettingValue NVARCHAR(MAX))")
            conn.commit()
            # Retry the logic or just return empty
            conn.close()
            return jsonify({})
        except:
            if conn: conn.close()
            return jsonify(bake(str(e))), 500

# --- CUSTOMERS & VEHICLES ---
@app.route("/api/customers", methods=["GET", "POST", "PUT"])
def customers():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)

        if request.method == "GET":
            cursor.execute("""
                SELECT c.*, 
                CASE 
                    WHEN c.ReferralCode IS NOT NULL AND c.ReferralCode <> '' 
                    THEN (SELECT COUNT(*) FROM CustomerList WHERE ReferredBy = c.ReferralCode) 
                    ELSE 0 
                END as ReferralCount
                FROM CustomerList c
            """)
            rows = cursor.fetchall()
            conn.close()
            return jsonify(rows)

        elif request.method == "POST":
            data = request.json
            cust_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO CustomerList (CustomerId, LastName, FirstName, MiddleName, MobileNumber, CustomerAddress, ReferralCode, ReferredBy) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (cust_id, data.get("LastName"), data.get("FirstName"), data.get("MiddleName"), data.get("MobileNumber"), data.get("CustomerAddress"), data.get("ReferralCode"), data.get("ReferredBy"))
            )
            log_activity(cursor, f"Added customer {data.get('FirstName')} {data.get('LastName')}")
            conn.commit()
            conn.close()
            return jsonify({"CustomerId": cust_id})

        elif request.method == "PUT":
            data = request.json
            cursor.execute(
                "UPDATE CustomerList SET LastName=%s, FirstName=%s, MiddleName=%s, MobileNumber=%s, CustomerAddress=%s, ReferralCode=%s, ReferredBy=%s WHERE CustomerId=%s",
                (data.get("LastName"), data.get("FirstName"), data.get("MiddleName"), data.get("MobileNumber"), data.get("CustomerAddress"), data.get("ReferralCode"), data.get("ReferredBy"), data.get("CustomerId"))
            )
            log_activity(cursor, f"Updated customer {data.get('CustomerId')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Updated successfully"))

    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/vehicles", methods=["GET", "POST", "PUT"])
def vehicles():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)

        if request.method == "GET":
            cursor.execute("SELECT * FROM VehicleList")
            rows = cursor.fetchall()
            conn.close()
            return jsonify(rows)

        elif request.method == "POST":
            data = request.json
            veh_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO VehicleList (VehicleId, VehicleBrand, VehicleModel, VehicleSize, PlateNumber, CustomerId) VALUES (%s, %s, %s, %s, %s, %s)",
                (veh_id, data.get("VehicleBrand"), data.get("VehicleModel"), data.get("VehicleSize"), data.get("PlateNumber"), data.get("CustomerId"))
            )
            log_activity(cursor, f"Added vehicle {data.get('PlateNumber')} for customer {data.get('CustomerId')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Added successfully"))

        elif request.method == "PUT":
            data = request.json
            cursor.execute(
                "UPDATE VehicleList SET VehicleBrand=%s, VehicleModel=%s, VehicleSize=%s, PlateNumber=%s WHERE VehicleId=%s",
                (data.get("VehicleBrand"), data.get("VehicleModel"), data.get("VehicleSize"), data.get("PlateNumber"), data.get("VehicleId"))
            )
            log_activity(cursor, f"Updated vehicle {data.get('VehicleId')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Updated successfully"))

    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/vehicles/<vehicle_id>", methods=["DELETE"])
def delete_vehicle(vehicle_id):
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute("DELETE FROM VehicleList WHERE VehicleId = %s", (vehicle_id,))
        log_activity(cursor, f"Deleted vehicle {vehicle_id}")
        conn.commit()
        conn.close()
        return jsonify(bake("Deleted successfully"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- USERS ---
@app.route("/api/users", methods=["GET", "POST", "PUT"])
def users():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)

        # Ensure columns exist
        try:
            cursor.execute("IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('UserList') AND name = 'DailyRate') ALTER TABLE UserList ADD DailyRate DECIMAL(10, 2) DEFAULT 0")
            cursor.execute("IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('UserList') AND name = 'ScheduleTime') ALTER TABLE UserList ADD ScheduleTime NVARCHAR(255)")
            cursor.execute("IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('UserList') AND name = 'LastLogin') ALTER TABLE UserList ADD LastLogin NVARCHAR(255)")
            conn.commit()
        except:
            pass

        if request.method == "GET":
            cursor.execute("SELECT Username, DailyRate, ScheduleTime, LastLogin, 'user' as Role FROM UserList")
            users = cursor.fetchall()
            
            # Ensure AdminList exists (it should, but just in case)
            cursor.execute("SELECT Username, 0 as DailyRate, '' as ScheduleTime, '' as LastLogin, 'admin' as Role FROM AdminList")
            admins = cursor.fetchall()
            
            conn.close()
            return jsonify(users + admins)

        elif request.method == "POST":
            data = request.json
            role = data.get("Role", "user")
            
            if role == "admin":
                cursor.execute(
                    "INSERT INTO AdminList (Username, Password) VALUES (%s, %s)",
                    (data.get("Username"), data.get("Password"))
                )
            else:
                cursor.execute(
                    "INSERT INTO UserList (Username, Password, DailyRate, ScheduleTime) VALUES (%s, %s, %s, %s)",
                    (data.get("Username"), data.get("Password"), data.get("DailyRate", 0), data.get("ScheduleTime"))
                )
            log_activity(cursor, f"Added {role} {data.get('Username')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Added successfully"))

        elif request.method == "PUT":
            data = request.json
            role = data.get("Role", "user")
            
            if role == "admin":
                if data.get("Password"):
                    cursor.execute(
                        "UPDATE AdminList SET Password=%s WHERE Username=%s",
                        (data.get("Password"), data.get("Username"))
                    )
            else:
                if data.get("Password"):
                    cursor.execute(
                        "UPDATE UserList SET Password=%s, DailyRate=%s, ScheduleTime=%s WHERE Username=%s",
                        (data.get("Password"), data.get("DailyRate", 0), data.get("ScheduleTime"), data.get("Username"))
                    )
                else:
                    cursor.execute(
                        "UPDATE UserList SET DailyRate=%s, ScheduleTime=%s WHERE Username=%s",
                        (data.get("DailyRate", 0), data.get("ScheduleTime"), data.get("Username"))
                    )
            log_activity(cursor, f"Updated {role} {data.get('Username')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Updated successfully"))

    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- SERVICES & PACKAGES ---
@app.route("/api/services", methods=["GET", "POST", "PUT"])
def services():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        
        if request.method == "GET":
            cursor.execute("SELECT * FROM ServiceList")
            rows = cursor.fetchall()
            conn.close()
            return jsonify(rows)
            
        elif request.method == "POST":
            data = request.json
            cursor.execute(
                "INSERT INTO ServiceList (ServiceId, ServiceName, ServicePriceSizeS, ServicePriceSizeM, ServicePriceSizeL, ServicePriceSizeXL, ServicePriceSizeXXL, ServiceStatus) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (data.get("ServiceId"), data.get("ServiceName"), data.get("ServicePriceSizeS"), data.get("ServicePriceSizeM"), data.get("ServicePriceSizeL"), data.get("ServicePriceSizeXL"), data.get("ServicePriceSizeXXL"), data.get("ServiceStatus"))
            )
            log_activity(cursor, f"Added service {data.get('ServiceName')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Added successfully"))
            
        elif request.method == "PUT":
            data = request.json
            cursor.execute(
                "UPDATE ServiceList SET ServiceName=%s, ServicePriceSizeS=%s, ServicePriceSizeM=%s, ServicePriceSizeL=%s, ServicePriceSizeXL=%s, ServicePriceSizeXXL=%s, ServiceStatus=%s WHERE ServiceId=%s",
                (data.get("ServiceName"), data.get("ServicePriceSizeS"), data.get("ServicePriceSizeM"), data.get("ServicePriceSizeL"), data.get("ServicePriceSizeXL"), data.get("ServicePriceSizeXXL"), data.get("ServiceStatus"), data.get("ServiceId"))
            )
            log_activity(cursor, f"Updated service {data.get('ServiceId')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Updated successfully"))
            
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/extras", methods=["GET", "POST", "PUT", "DELETE"])
def extras():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        
        # Ensure table exists
        try:
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ExtrasList' and xtype='U')
                CREATE TABLE ExtrasList (
                    ExtraId NVARCHAR(255) PRIMARY KEY,
                    ExtraName NVARCHAR(255),
                    ExtraPrice DECIMAL(10, 2),
                    ExtraType NVARCHAR(50),
                    ExtraStatus NVARCHAR(50)
                )
            """)
            conn.commit()
        except Exception as e:
            print("Table check/create error (ExtrasList):", e)
            
        if request.method == "GET":
            cursor.execute("SELECT * FROM ExtrasList")
            rows = cursor.fetchall()
            conn.close()
            return jsonify(rows)
            
        elif request.method == "POST":
            data = request.json
            extra_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO ExtrasList (ExtraId, ExtraName, ExtraPrice, ExtraType, ExtraStatus) VALUES (%s, %s, %s, %s, %s)",
                (extra_id, data.get("ExtraName"), data.get("ExtraPrice"), data.get("ExtraType"), data.get("ExtraStatus", "Available"))
            )
            log_activity(cursor, f"Added extra {data.get('ExtraName')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Added successfully"))
            
        elif request.method == "PUT":
            data = request.json
            cursor.execute(
                "UPDATE ExtrasList SET ExtraName=%s, ExtraPrice=%s, ExtraType=%s, ExtraStatus=%s WHERE ExtraId=%s",
                (data.get("ExtraName"), data.get("ExtraPrice"), data.get("ExtraType"), data.get("ExtraStatus"), data.get("ExtraId"))
            )
            log_activity(cursor, f"Updated extra {data.get('ExtraId')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Updated successfully"))
            
        elif request.method == "DELETE":
            extra_id = request.args.get("ExtraId")
            cursor.execute("DELETE FROM ExtrasList WHERE ExtraId = %s", (extra_id,))
            log_activity(cursor, f"Deleted extra {extra_id}")
            conn.commit()
            conn.close()
            return jsonify(bake("Deleted successfully"))
            
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/service-special-prices", methods=["GET", "POST", "DELETE"])
def service_special_prices():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        
        # Ensure table exists
        try:
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ServiceVehiclePriceList' and xtype='U')
                CREATE TABLE ServiceVehiclePriceList (
                    Id INT IDENTITY(1,1) PRIMARY KEY,
                    ServiceId NVARCHAR(255),
                    VehicleBrand NVARCHAR(255),
                    VehicleModel NVARCHAR(255),
                    SpecialPrice DECIMAL(10, 2)
                )
            """)
            conn.commit()
        except Exception as e:
            print("Table check/create error:", e)
            
        if request.method == "GET":
            cursor.execute("SELECT * FROM ServiceVehiclePriceList")
            rows = cursor.fetchall()
            conn.close()
            return jsonify(rows)
            
        elif request.method == "POST":
            data = request.json
            # Check if exists to update or insert
            cursor.execute(
                "SELECT * FROM ServiceVehiclePriceList WHERE ServiceId = %s AND VehicleBrand = %s AND VehicleModel = %s",
                (data.get("ServiceId"), data.get("VehicleBrand"), data.get("VehicleModel"))
            )
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE ServiceVehiclePriceList SET SpecialPrice = %s WHERE ServiceId = %s AND VehicleBrand = %s AND VehicleModel = %s",
                    (data.get("SpecialPrice"), data.get("ServiceId"), data.get("VehicleBrand"), data.get("VehicleModel"))
                )
            else:
                cursor.execute(
                    "INSERT INTO ServiceVehiclePriceList (ServiceId, VehicleBrand, VehicleModel, SpecialPrice) VALUES (%s, %s, %s, %s)",
                    (data.get("ServiceId"), data.get("VehicleBrand"), data.get("VehicleModel"), data.get("SpecialPrice"))
                )
            log_activity(cursor, f"Set special price for {data.get('ServiceId')} on {data.get('VehicleBrand')} {data.get('VehicleModel')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Special price saved"))
            
        elif request.method == "DELETE":
            data = request.json
            cursor.execute(
                "DELETE FROM ServiceVehiclePriceList WHERE ServiceId = %s AND VehicleBrand = %s AND VehicleModel = %s",
                (data.get("ServiceId"), data.get("VehicleBrand"), data.get("VehicleModel"))
            )
            log_activity(cursor, f"Removed special price for {data.get('ServiceId')} on {data.get('VehicleBrand')} {data.get('VehicleModel')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Special price removed"))
            
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/packages", methods=["GET"])
def packages():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT * FROM PackageList WHERE PackageStatus = 'Available'")
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- TRANSACTIONS & BILLING ---
@app.route("/api/transactions", methods=["GET", "POST", "PUT"])
def transactions():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)

        if request.method == "GET":
            cursor.execute("SELECT * FROM TransactionList ORDER BY DateCreated DESC, DateUpdated DESC")
            rows = cursor.fetchall()
            conn.close()
            return jsonify(rows)

        elif request.method == "POST":
            data = request.json
            trans_id = str(uuid.uuid4())
            now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute(
                "INSERT INTO TransactionList (TransactionId, EmployeeIdList, ServiceIdList, PackageId, Extras, VehicleId, TransactionStatus, DateCreated, DateUpdated) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (trans_id, data.get("EmployeeIdList"), data.get("ServiceIdList"), data.get("PackageId"), data.get("Extras"), data.get("VehicleId"), "Ready", now, now)
            )
            
            # Create Billing
            bill_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO BillingList (BillingId, TransactionBalance, TransactionDiscount, BalancePaid, BillingStatus, DateCreated, DateUpdated) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (trans_id, data.get("TotalBalance"), data.get("Discount"), 0, "Unpaid", now, now)
            )

            log_activity(cursor, f"Created transaction {trans_id}")
            conn.commit()
            conn.close()
            return jsonify(bake("Transaction created"))

        elif request.method == "PUT":
            data = request.json
            now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
            
            if "TransactionStatus" in data and len(data.keys()) <= 2:
                # Simple status update
                cursor.execute(
                    "UPDATE TransactionList SET TransactionStatus=%s, DateUpdated=%s WHERE TransactionId=%s",
                    (data.get("TransactionStatus"), now, data.get("TransactionId"))
                )
                log_activity(cursor, f"Updated transaction {data.get('TransactionId')} status to {data.get('TransactionStatus')}")
            else:
                # Full update (for editing Ready transactions)
                cursor.execute(
                    "UPDATE TransactionList SET EmployeeIdList=%s, ServiceIdList=%s, PackageId=%s, Extras=%s, VehicleId=%s, DateUpdated=%s WHERE TransactionId=%s",
                    (data.get("EmployeeIdList"), data.get("ServiceIdList"), data.get("PackageId"), data.get("Extras"), data.get("VehicleId"), now, data.get("TransactionId"))
                )
                
                # Update Billing
                cursor.execute(
                    "UPDATE BillingList SET TransactionBalance=%s, TransactionDiscount=%s, DateUpdated=%s WHERE BillingId=%s",
                    (data.get("TotalBalance"), data.get("Discount"), now, data.get("TransactionId"))
                )
                log_activity(cursor, f"Edited transaction {data.get('TransactionId')}")
                
            conn.commit()
            conn.close()
            return jsonify(bake("Updated successfully"))

    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/billing", methods=["GET", "PUT"])
def billing():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)

        if request.method == "GET":
            cursor.execute("SELECT * FROM BillingList")
            rows = cursor.fetchall()
            conn.close()
            return jsonify(rows)

        elif request.method == "PUT":
            data = request.json
            now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "UPDATE BillingList SET BalancePaid=%s, BillingStatus=%s, DateUpdated=%s WHERE BillingId=%s",
                (data.get("BalancePaid"), data.get("BillingStatus"), now, data.get("BillingId"))
            )
            log_activity(cursor, f"Updated billing {data.get('BillingId')} to {data.get('BillingStatus')}")
            conn.commit()
            conn.close()
            return jsonify(bake("Payment recorded"))

    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- REPORTS & ACTIVITY ---
@app.route("/api/reports", methods=["GET"])
def reports():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        # Simplified report logic based on BillingList DateUpdated
        cursor.execute("SELECT DateUpdated, TransactionBalance, BalancePaid, TransactionDiscount FROM BillingList WHERE BillingStatus = 'Paid'")
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/activity", methods=["GET"])
def activity():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        
        # Ensure ActivityDate column exists
        try:
            cursor.execute("IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('ActivityList') AND name = 'ActivityDate') ALTER TABLE ActivityList ADD ActivityDate NVARCHAR(255)")
            conn.commit()
        except:
            pass

        cursor.execute("SELECT * FROM ActivityList ORDER BY ActivityDate DESC") 
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
