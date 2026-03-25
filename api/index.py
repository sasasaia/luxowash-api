from flask import Flask, jsonify, request
from flask_cors import CORS
import pymssql
import os
import jwt
import datetime
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

from flask.json import JSONEncoder

class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return super().default(obj)

app = Flask(__name__)
app.json_encoder = CustomJSONEncoder
CORS(app)

# Configuration
JWT_SECRET = os.environ.get("JWT_SECRET", "luxowash_secret_key_2026")
JSON_RESPONSE_TITLE = "response_data"

def bake(message):
    return {JSON_RESPONSE_TITLE: message, "message": message}

def get_connection():
    return pymssql.connect(
        server=os.environ.get("DB_SERVER"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASS"),
        database=os.environ.get("DB_NAME"),
        as_dict=True
    )

# Auth Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify(bake("Token is missing")), 401
        
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            current_user = data
        except:
            return jsonify(bake("Token is invalid")), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

def log_activity(message):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ActivityList (ActivityMessage) VALUES (%s)", (message,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Logging error: {e}")

@app.route("/")
def home():
    return jsonify(bake("Luxowash Python API"))

# --- Auth Routes ---
@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.json
        username = data.get("username")
        password = data.get("password")
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check AdminList
        cursor.execute("SELECT * FROM AdminList WHERE Username = %s AND Password = %s", (username, password))
        user = cursor.fetchone()
        role = "admin"
        
        if not user:
            # Check UserList
            cursor.execute("SELECT * FROM UserList WHERE Username = %s AND Password = %s", (username, password))
            user = cursor.fetchone()
            role = "user"
            
        conn.close()
        
        if user:
            token = jwt.encode({
                'username': username,
                'role': role,
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            }, JWT_SECRET, algorithm="HS256")
            
            log_activity(f"User {username} logged in as {role}")
            return jsonify({
                "token": token,
                "username": username,
                "role": role
            })
        else:
            return jsonify(bake("Invalid credentials")), 401
            
    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- Employee Routes ---
@app.route("/api/employees", methods=["GET"])
@token_required
def get_employees(current_user):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM EmployeeList")
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/employees", methods=["POST"])
@token_required
def add_employee(current_user):
    try:
        data = request.json
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO EmployeeList (EmployeeId, LastName, FirstName, MiddleName, MobileNumber, EmployeeAddress)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            data.get("EmployeeId"), data.get("LastName"), data.get("FirstName"),
            data.get("MiddleName"), data.get("MobileNumber"), data.get("EmployeeAddress")
        ))
        conn.commit()
        conn.close()
        log_activity(f"Added employee {data.get('FirstName')} {data.get('LastName')}")
        return jsonify(bake("Added successfully"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/employees/<id>", methods=["PUT"])
@token_required
def update_employee(current_user, id):
    try:
        data = request.json
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE EmployeeList 
            SET LastName=%s, FirstName=%s, MiddleName=%s, MobileNumber=%s, EmployeeAddress=%s 
            WHERE EmployeeId=%s
        """, (
            data.get("LastName"), data.get("FirstName"), data.get("MiddleName"),
            data.get("MobileNumber"), data.get("EmployeeAddress"), id
        ))
        conn.commit()
        conn.close()
        log_activity(f"Updated employee {id}")
        return jsonify(bake("Updated successfully"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- Time Tracking ---
@app.route("/api/employees/time", methods=["GET"])
@token_required
def get_time_logs(current_user):
    try:
        today = datetime.date.today().isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM EmployeeTimeList WHERE DateCreated = %s", (today,))
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/employees/time-in", methods=["POST"])
@token_required
def time_in(current_user):
    try:
        data = request.json
        employee_id = data.get("EmployeeId")
        now = datetime.datetime.now()
        time_str = now.strftime("%I:%M:%S %p")
        date_str = now.date().isoformat()
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO EmployeeTimeList (EmployeeId, TimeIn, DateCreated) VALUES (%s, %s, %s)", 
                       (employee_id, time_str, date_str))
        conn.commit()
        conn.close()
        log_activity(f"Employee {employee_id} timed in at {time_str}")
        return jsonify(bake("Timed in successfully"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/employees/time-out", methods=["POST"])
@token_required
def time_out(current_user):
    try:
        data = request.json
        employee_id = data.get("EmployeeId")
        now = datetime.datetime.now()
        time_str = now.strftime("%I:%M:%S %p")
        date_str = now.date().isoformat()
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE EmployeeTimeList 
            SET TimeOut = %s 
            WHERE EmployeeId = %s AND DateCreated = %s AND TimeOut IS NULL
        """, (time_str, employee_id, date_str))
        conn.commit()
        conn.close()
        log_activity(f"Employee {employee_id} timed out at {time_str}")
        return jsonify(bake("Timed out successfully"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- Customer & Vehicle Routes ---
@app.route("/api/customers", methods=["GET"])
@token_required
def get_customers(current_user):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM CustomerList")
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/customers", methods=["POST"])
@token_required
def add_customer(current_user):
    try:
        data = request.json
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO CustomerList (CustomerId, LastName, FirstName, MiddleName, PlateNumbers, MobileNumber, CustomerAddress)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get("CustomerId"), data.get("LastName"), data.get("FirstName"),
            data.get("MiddleName"), data.get("PlateNumbers"), data.get("MobileNumber"), data.get("CustomerAddress")
        ))
        conn.commit()
        conn.close()
        log_activity(f"Added customer {data.get('FirstName')} {data.get('LastName')}")
        return jsonify(bake("Added successfully"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/vehicles", methods=["GET"])
@token_required
def get_vehicles(current_user):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM VehicleList")
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/vehicles", methods=["POST"])
@token_required
def add_vehicle(current_user):
    try:
        data = request.json
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO VehicleList (VehicleId, VehicleBrand, VehicleModel, VehicleSize, PlateNumber, CustomerId)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            data.get("VehicleId"), data.get("VehicleBrand"), data.get("VehicleModel"),
            data.get("VehicleSize"), data.get("PlateNumber"), data.get("CustomerId")
        ))
        conn.commit()
        conn.close()
        log_activity(f"Added vehicle {data.get('PlateNumber')}")
        return jsonify(bake("Added successfully"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- Package & Service Routes ---
@app.route("/api/packages", methods=["GET"])
@token_required
def get_packages(current_user):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM PackageList")
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/services", methods=["GET"])
@token_required
def get_services(current_user):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ServiceList")
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- Transaction & Billing Routes ---
@app.route("/api/transactions", methods=["GET"])
@token_required
def get_transactions(current_user):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM TransactionList")
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/transactions", methods=["POST"])
@token_required
def add_transaction(current_user):
    try:
        data = request.json
        billing = data.get("Billing")
        now = datetime.datetime.now().isoformat()
        date_str = now.split('T')[0]
        
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO TransactionList (TransactionId, EmployeeIdList, ServiceIdList, PackageId, Extras, VehicleId, TransactionStatus, DateUpdated, DateCreated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get("TransactionId"), data.get("EmployeeIdList"), data.get("ServiceIdList"),
            data.get("PackageId"), data.get("Extras"), data.get("VehicleId"),
            data.get("TransactionStatus"), now, date_str
        ))
        
        cursor.execute("""
            INSERT INTO BillingList (BillingId, TransactionBalance, TransactionDiscount, BalancePaid, BillingStatus, DateUpdated, DateCreated)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get("TransactionId"), billing.get("TransactionBalance"), billing.get("TransactionDiscount"),
            billing.get("BalancePaid"), billing.get("BillingStatus"), now, date_str
        ))
        
        conn.commit()
        conn.close()
        log_activity(f"Created transaction {data.get('TransactionId')}")
        return jsonify(bake("Added successfully"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/transactions/<id>", methods=["PUT"])
@token_required
def update_transaction(current_user, id):
    try:
        data = request.json
        status = data.get("TransactionStatus")
        now = datetime.datetime.now().isoformat()
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE TransactionList SET TransactionStatus = %s, DateUpdated = %s WHERE TransactionId = %s", 
                       (status, now, id))
        conn.commit()
        conn.close()
        log_activity(f"Updated transaction {id} to {status}")
        return jsonify(bake("Updated successfully"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/billing", methods=["GET"])
@token_required
def get_billing(current_user):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM BillingList")
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/billing/<id>", methods=["PUT"])
@token_required
def update_billing(current_user, id):
    try:
        data = request.json
        now = datetime.datetime.now().isoformat()
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE BillingList 
            SET BalancePaid = %s, BillingStatus = %s, DateUpdated = %s 
            WHERE BillingId = %s
        """, (data.get("BalancePaid"), data.get("BillingStatus"), now, id))
        conn.commit()
        conn.close()
        log_activity(f"Updated billing for {id}")
        return jsonify(bake("Updated successfully"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- User Management ---
@app.route("/api/users", methods=["GET"])
@token_required
def get_users(current_user):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Username, 'admin' as role FROM AdminList")
        admins = cursor.fetchall()
        cursor.execute("SELECT Username, 'user' as role FROM UserList")
        users = cursor.fetchall()
        conn.close()
        return jsonify(admins + users)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/users", methods=["POST"])
@token_required
def add_user(current_user):
    try:
        data = request.json
        username = data.get("Username")
        password = data.get("Password")
        role = data.get("role")
        
        conn = get_connection()
        cursor = conn.cursor()
        if role == 'admin':
            cursor.execute("INSERT INTO AdminList (Username, Password) VALUES (%s, %s)", (username, password))
        else:
            cursor.execute("INSERT INTO UserList (Username, Password) VALUES (%s, %s)", (username, password))
        conn.commit()
        conn.close()
        log_activity(f"Added {role} account: {username}")
        return jsonify(bake("Added successfully"))
    except Exception as e:
        return jsonify(bake(str(e))), 500

# --- Reports & Activity ---
@app.route("/api/activity", methods=["GET"])
@token_required
def get_activity(current_user):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TOP 100 * FROM ActivityList ORDER BY Timestamp DESC")
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/reports/sales", methods=["GET"])
@token_required
def get_sales_report(current_user):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DateCreated, SUM(BalancePaid) as TotalSales 
            FROM BillingList 
            WHERE BillingStatus = 'Paid' 
            GROUP BY DateCreated 
            ORDER BY DateCreated DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify(bake(str(e))), 500

def create_tables():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Create tables if they don't exist
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ActivityList')
            CREATE TABLE ActivityList (
                ActivityMessage NVARCHAR(MAX),
                Timestamp DATETIME DEFAULT GETDATE()
            );
            
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'AdminList')
            CREATE TABLE AdminList (
                Username NVARCHAR(50) PRIMARY KEY,
                Password NVARCHAR(255)
            );
            
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserList')
            CREATE TABLE UserList (
                Username NVARCHAR(50) PRIMARY KEY,
                Password NVARCHAR(255)
            );
            
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'BillingList')
            CREATE TABLE BillingList (
                BillingId NVARCHAR(50) PRIMARY KEY,
                TransactionBalance FLOAT,
                TransactionDiscount FLOAT,
                BalancePaid FLOAT,
                BillingStatus NVARCHAR(50),
                DateUpdated NVARCHAR(50),
                DateCreated NVARCHAR(50)
            );
            
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'CustomerList')
            CREATE TABLE CustomerList (
                CustomerId NVARCHAR(50) PRIMARY KEY,
                LastName NVARCHAR(100),
                FirstName NVARCHAR(100),
                MiddleName NVARCHAR(100),
                PlateNumbers NVARCHAR(MAX),
                MobileNumber NVARCHAR(50),
                CustomerAddress NVARCHAR(MAX)
            );
            
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'EmployeeList')
            CREATE TABLE EmployeeList (
                EmployeeId NVARCHAR(50) PRIMARY KEY,
                LastName NVARCHAR(100),
                FirstName NVARCHAR(100),
                MiddleName NVARCHAR(100),
                EmployeeDocuments NVARCHAR(MAX),
                MobileNumber NVARCHAR(50),
                EmployeeAddress NVARCHAR(MAX)
            );
            
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'EmployeeTimeList')
            CREATE TABLE EmployeeTimeList (
                EmployeeId NVARCHAR(50),
                TimeIn NVARCHAR(50),
                TimeOut NVARCHAR(50),
                DateCreated NVARCHAR(50)
            );
            
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'PackageList')
            CREATE TABLE PackageList (
                PackageId NVARCHAR(50) PRIMARY KEY,
                PackageName NVARCHAR(100),
                PackageDetails NVARCHAR(MAX),
                PackagePriceSizeS FLOAT,
                PackagePriceSizeM FLOAT,
                PackagePriceSizeL FLOAT,
                PackagePriceSizeXL FLOAT,
                PackagePriceSizeXXL FLOAT,
                PackageStatus NVARCHAR(50)
            );
            
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ServiceList')
            CREATE TABLE ServiceList (
                ServiceId NVARCHAR(50) PRIMARY KEY,
                ServiceName NVARCHAR(100),
                ServicePriceSizeS FLOAT,
                ServicePriceSizeM FLOAT,
                ServicePriceSizeL FLOAT,
                ServicePriceSizeXL FLOAT,
                ServicePriceSizeXXL FLOAT,
                ServiceStatus NVARCHAR(50)
            );
            
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'TransactionList')
            CREATE TABLE TransactionList (
                TransactionId NVARCHAR(50) PRIMARY KEY,
                EmployeeIdList NVARCHAR(MAX),
                ServiceIdList NVARCHAR(MAX),
                PackageId NVARCHAR(50),
                Extras NVARCHAR(MAX),
                VehicleId NVARCHAR(50),
                TransactionStatus NVARCHAR(50),
                DateUpdated NVARCHAR(50),
                DateCreated NVARCHAR(50)
            );
            
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'VehicleList')
            CREATE TABLE VehicleList (
                VehicleId NVARCHAR(50) PRIMARY KEY,
                VehicleBrand NVARCHAR(100),
                VehicleModel NVARCHAR(100),
                VehicleSize NVARCHAR(50),
                PlateNumber NVARCHAR(50),
                CustomerId NVARCHAR(50)
            );
        """)
        
        # Seed initial data if empty
        cursor.execute("SELECT COUNT(*) as count FROM AdminList")
        if cursor.fetchone()['count'] == 0:
            cursor.execute("INSERT INTO AdminList (Username, Password) VALUES (%s, %s)", ("admin", "admin"))
            cursor.execute("INSERT INTO AdminList (Username, Password) VALUES (%s, %s)", ("test2", "test2"))
            
        cursor.execute("SELECT COUNT(*) as count FROM UserList")
        if cursor.fetchone()['count'] == 0:
            cursor.execute("INSERT INTO UserList (Username, Password) VALUES (%s, %s)", ("cashier", "cashier"))
            
        cursor.execute("SELECT COUNT(*) as count FROM PackageList")
        if cursor.fetchone()['count'] == 0:
            packages = [
                ('P_B','Basic','Wash,Armor All,Hand Wax,Under Wash',1000,1100,1200,1300,1600,'Available'),
                ('P_ST','Standard','Wash,Armor All,Hand Wax,Under Wash,Glass Detailing',2000,2200,2300,2500,3000,'Available'),
                ('P_D','Deluxe','Wash,Armor All,Asphalt Removal,Buff. Wax,Glass Detailing,BAC to Zero',2600,2900,3100,3300,4000,'Available'),
                ('P_U','Ultimate','Wash,Armor All,Asphalt Removal,Buff. Wax,Glass Detailing,Under Wash,BAC to Zero',3000,3300,3600,3900,4600,'Available'),
                ('P_SU','Superior','Wash,Armor All,3-Steps Buffing,Glass Detailing,Under Wash,BAC to Zero',4500,5000,5500,6000,7500,'Available')
            ]
            for p in packages:
                cursor.execute("INSERT INTO PackageList VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", p)
                
        cursor.execute("SELECT COUNT(*) as count FROM ServiceList")
        if cursor.fetchone()['count'] == 0:
            services = [
                ('S_BWV','Body Wash and Vacuum',140,160,180,200,250,'Available'),
                ('S_AA','Armor All',140,140,140,140,200,'Available'),
                ('S_AR','Asphalt Removal',200,230,250,280,350,'Available'),
                ('S_SCCR','Seat Cover - Cloth - Removal',150,200,250,250,300,'Available'),
                ('S_SCCI','Seat Cover - Cloth - Install',200,250,300,350,350,'Available'),
                ('S_SCCL','Seat Cover - Cloth - Laundry',150,150,200,200,250,'Available'),
                ('S_SCLR','Seat Cover - Leather - Removal',150,200,250,250,300,'Available'),
                ('S_SCLI','Seat Cover - Leather - Install',300,350,400,400,450,'Available'),
                ('S_SCLL','Seat Cover - Leather - Laundry',200,200,250,250,300,'Available'),
                ('S_DBTZ','Disinfection (Bac to Zero)',600,600,600,600,600,'Available'),
                ('S_HC','Headlights Cleaning',600,600,600,600,600,'Available'),
                ('S_EW','Engine Wash',700,700,700,700,700,'Available'),
                ('S_MC','Muffler Cleaning',500,600,700,800,1000,'Available'),
                ('S_DGD','Detailing - Glass Detailing',1000,1100,1200,1300,1600,'Available'),
                ('S_DB3S','Detailing - Buffing 3 Steps',2700,3200,3700,4200,5200,'Available'),
                ('S_DI','Detailing - Interior',3500,4000,4500,5000,6000,'Available'),
                ('S_DE','Detailing - Exterior',4000,4500,5000,5500,6500,'Available'),
                ('S_DF','Detailing - Full',7000,8000,9000,10000,12000,'Available'),
                ('S_U','Underwash',400,450,500,550,600,'Available'),
                ('S_UC','Under Coating',6000,6500,7000,7500,8500,'Available'),
                ('S_HWM','Hand Wax (Manual)',500,550,600,650,750,'Available'),
                ('S_BWM','Buff Wax (Machine)',900,100,1100,1200,1500,'Available'),
                ('S_CCBP','Ceramic Coating - Body Panels',15000,16000,17000,18000,20000,'Available'),
                ('S_CCG','Ceramic Coating - Glass',5000,6000,7000,8000,10000,'Available'),
                ('S_CCR','Ceramic Coating - Rims',3000,4000,5000,6000,6000,'Available'),
                ('S_RBWWOH','Repainting/Body Works - Wash Over (Hilamos)',30000,35000,40000,45000,50000,'Available'),
                ('S_RBWPPPSA','Repainting/Body Works - Per Panel Price Starts At',3500,3500,4000,4500,5000,'Available'),
                ('S_RBWRC','Repainting/Body Works - Rims - Car',5000,5000,6000,8000,8000,'Available'),
                ('S_VCBW_S','Body Wash S',120,120,120,120,120,'Available'),
                ('S_VCBW_M','Body Wash M',150,150,150,150,150,'Available'),
                ('S_VCBW_L','Body Wash L',200,200,200,200,200,'Available'),
                ('S_VCA','Armor',100,100,100,100,100,'Available'),
                ('S_VCW','Wax (Manual)',150,150,150,150,150,'Available')
            ]
            for s in services:
                cursor.execute("INSERT INTO ServiceList VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", s)
                
        cursor.execute("SELECT COUNT(*) as count FROM EmployeeList")
        if cursor.fetchone()['count'] == 0:
            employees = [
                ('1','BARRETTO','DOMINIC',None,None,None,None),
                ('2','LOLONG','ARJAY',None,None,None,None),
                ('3','CATALAN','HENRY',None,None,None,None),
                ('4','APIN','JOHN PAUL',None,None,None,None),
                ('5','AREVALO','PHILIP',None,None,None,None),
                ('6','CARULLO','JOHN CRIS',None,None,None,None),
                ('7','APIN','JEROME',None,None,None,None),
                ('8','SALAZAR','JOSHUA',None,None,None,None),
                ('9','AGUDO','LOWEI JAY',None,None,None,None),
                ('10','SALAZAR','SALVADOR',None,None,None,None),
                ('11','CARULLO','LARRY',None,None,None,None),
                ('12','NEPOMUCENO','GREG',None,None,None,None),
                ('13','CONOCIDO','JAIMIE',None,None,None,None)
            ]
            for e in employees:
                cursor.execute("INSERT INTO EmployeeList VALUES (%s,%s,%s,%s,%s,%s,%s)", e)
        
        conn.commit()
        conn.close()
        print("Database tables checked/created.")
    except Exception as e:
        print(f"Database initialization error: {e}")

if __name__ == "__main__":
    create_tables()
    app.run(port=5000)
