from flask import Flask, jsonify, request
from flask_cors import CORS
import pymssql
import sys
import os
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

@app.route("/")
def home():
    return jsonify(bake("insgi-be"))

@app.route("/about")
def about():
    return jsonify(bake(sys.version))

@app.route("/test")
def test():
    return jsonify(bake("Test JSON"))

@app.route("/api/test", methods=["GET"])
def get_test():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)

        cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME")
        rows = cursor.fetchall()

        conn.close()
        return jsonify(rows)

    except Exception as e:
        return jsonify(bake(str(e))), 500

# @app.route("/api/clear", methods=["GET"])
# def clear_data():
#     try:
#         if request.args.get("c") == "go":
#             conn = get_connection()
#             cursor = conn.cursor()
#
#             cursor.execute("TRUNCATE TABLE attendance_table")
#             conn.commit()
#             conn.close()
#
#         return jsonify("Done")
#     except Exception as e:
#         return jsonify(bake(str(e))), 500

@app.route("/api/attendance", methods=["GET"])
def get_data():
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)

        conn.cursor().execute("""
        IF NOT EXISTS (
            SELECT * FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'attendance_table'
        )
        BEGIN
            CREATE TABLE attendance_table (
                id NVARCHAR(MAX),
                time_in NVARCHAR(MAX),
                time_out NVARCHAR(MAX),
                time_in_photo NVARCHAR(MAX),
                time_out_photo NVARCHAR(MAX),
                date NVARCHAR(MAX)
            )
        END
        """)
        conn.commit()

        cursor.execute("SELECT id, time_in, time_out, time_in_photo, time_out_photo, date FROM attendance_table")
        rows = cursor.fetchall()

        conn.close()
        return jsonify(rows)

    except Exception as e:
        return jsonify(bake(str(e))), 500

@app.route("/api/attendance", methods=["POST"])
def insert_data():
    try:
        data = request.json
        data_id = data.get("id")
        time_in = data.get("time_in")
        time_out = data.get("time_out")
        time_in_photo = data.get("time_in_photo")
        time_out_photo = data.get("time_out_photo")
        date = data.get("date")

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        IF NOT EXISTS (
            SELECT * FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'attendance_table'
        )
        BEGIN
            CREATE TABLE attendance_table (
                id NVARCHAR(MAX),
                time_in NVARCHAR(MAX),
                time_out NVARCHAR(MAX),
                time_in_photo NVARCHAR(MAX),
                time_out_photo NVARCHAR(MAX),
                date NVARCHAR(MAX)
            )
        END
        """)

        cursor.execute(
            "INSERT INTO attendance_table (id, time_in, time_out, time_in_photo, time_out_photo, date) VALUES (%s, %s, %s, %s, %s, %s)",
            (data_id, time_in, time_out, time_in_photo, time_out_photo, date)
        )
        conn.commit()
        conn.close()

        return jsonify(bake("Added successfully"))

    except Exception as e:
        return jsonify(bake(str(e))), 500
