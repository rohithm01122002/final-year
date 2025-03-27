import sqlite3
import json
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import http.server
import socketserver
import re

# Define states for conversation
(NAME, CONTACT, ADDRESS, START_HOUR, END_HOUR, CAR_NUMBER, BOOK_SLOT) = range(7)

# Database schema update to add slot_booked column if missing

def update_database_schema():
    conn = sqlite3.connect("parking_backup.db")
    cursor = conn.cursor()

    # Check if the 'slot_booked' column exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if "slot_booked" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN slot_booked TEXT DEFAULT 'No'")
        conn.commit()

    conn.close()




# Telegram Bot logic
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Welcome to Smart Car Parking! Please enter your name:")
    return NAME

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Enter your contact number:")
    return CONTACT

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact_number = update.message.text.strip()

    if not contact_number.isdigit() or len(contact_number) != 10:
        await update.message.reply_text("Invalid contact number. Number must contain 10 digits.")
        return CONTACT

    context.user_data['contact'] = contact_number
    await update.message.reply_text("Enter your address:\nBuilding no., Street name, City, State, Pincode")
    return ADDRESS

async def address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['address'] = update.message.text
    await update.message.reply_text("Enter your parking start hour:")
    return START_HOUR

async def start_hour(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_pattern = r'^(0?[1-9]|1[0-2]):([0-5][0-9])([apAP][mM])$'
    start_hour_input = update.message.text.strip()

    if not re.match(time_pattern, start_hour_input):
        await update.message.reply_text("Invalid time format. Please enter the time in the format 'H:MMam' or 'H:MMpm'. For example: 2:00am or 3:30pm.")
        return START_HOUR

    context.user_data['start_hour'] = start_hour_input
    await update.message.reply_text("Enter your parking end hour:")
    return END_HOUR

async def end_hour(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_pattern = r'^(0?[1-9]|1[0-2]):([0-5][0-9])([apAP][mM])$'
    end_hour_input = update.message.text.strip()

    if not re.match(time_pattern, end_hour_input):
        await update.message.reply_text("Invalid time format. Please enter the time in the format 'H:MMam' or 'H:MMpm'. For example: 2:00am or 3:30pm.")
        return END_HOUR

    context.user_data['end_hour'] = end_hour_input
    await update.message.reply_text("Enter your car number:")
    return CAR_NUMBER

async def car_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    car_number = update.message.text.strip()

    car_number_pattern = r'^[A-Za-z]{2}\d{2}[A-Za-z]{2}\d{4}$'

    if not re.match(car_number_pattern, car_number):
        await update.message.reply_text("Invalid car number. The format should be: 'XX00XX0000' (e.g., KA01AB1234). Please enter again.")
        return CAR_NUMBER

    context.user_data['car_number'] = car_number
    save_to_db(context.user_data)
    export_to_json()
    await update.message.reply_text("Your registration is complete! Type 'book slot' to book a parking slot.\nAvailable slots are only 5 Slots.")
    return BOOK_SLOT

async def book_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()

    if text == "book slot":
        if parking_slots:
            available_slots = [slot for slot in parking_slots if slot["status"] == "available"]
            if available_slots:
                slot = available_slots[0]  # Book the first available slot
                slot["status"] = "booked"
                await update.message.reply_text(f"Slot {slot['id']} has been booked for you.\nRemaining slots: {len(available_slots) - 1}.")

                remaining_slots = [slot for slot in parking_slots if slot["status"] == "available"]
                if not remaining_slots:
                    await update.message.reply_text("Sorry, no slots are available in Parkz. Check other locations or book later. Thank you! :)")
                    return ConversationHandler.END

                await update.message.reply_text("Would you like to book another slot? Type 'book slot' or type 'exit' to end.")
            else:
                await update.message.reply_text("Sorry, no slots are available in Parkz. Check other locations or book later. Thank you! :)")
                return ConversationHandler.END
        else:
            await update.message.reply_text("No parking slots are available.")
            return ConversationHandler.END

    elif text == "exit":
        await update.message.reply_text("Thank you for visiting our Parkz Bot.. Have a nice day!")
        await update.message.reply_text("To book a slot, you must clear the history and click 'Start' again for re-registration.")
        return ConversationHandler.END

    else:
        await update.message.reply_text("Invalid command. Type 'book slot' to book a parking slot or 'exit' to end.")
    return BOOK_SLOT

async def handle_other_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text.strip().lower()

    if user_text not in ["customer registration", "book slot", "exit", "cancel", "available slots", "empty slots", "visit website"]:
        await update.message.reply_text("Sorry, I didn't quite get that. How can I assist you? Type 'exit' to end the conversation or choose from the menu below.")

    await update.message.reply_text("Here are some options:\n"
                                    "1. Customer Registration\n"
                                    "2. Book Slot\n"
                                    "3. Exit\n"
                                    "4. Cancel\n"
                                    "5. Available Slots\n"
                                    "6. Empty Slots\n"
                                    "7. Visit Website")

# Initialize parking slots
parking_slots = [{"id": i, "status": "available"} for i in range(1, 6)]

# Database functions
def save_to_db(data):
    conn = sqlite3.connect("parking_backup.db")
    cursor = conn.cursor()

    # Ensure the table has the correct schema
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        name TEXT,
                        contact TEXT,
                        address TEXT,
                        start_hour TEXT,
                        end_hour TEXT,
                        car_number TEXT,
                        slot_booked TEXT)''')

    cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (data['name'], data['contact'], data['address'], data['start_hour'], data['end_hour'], data['car_number'], "Yes"))
    conn.commit()
    conn.close()

def export_to_json():
    conn = sqlite3.connect("parking_backup.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()

    user_list = [{"name": user[0], "contact": user[1], "address": user[2],
                  "start_hour": user[3], "end_hour": user[4], "car_number": user[5], "slot_booked": user[6]} for user in users]

    with open("data.json", "w") as f:
        json.dump(user_list, f)

class WebsiteHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/slots":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(parking_slots).encode())
        elif self.path == "/users":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            with open("data.json", "r") as f:
                self.wfile.write(f.read().encode())
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            with open("regist.html", "r") as file:
                self.wfile.write(file.read().encode())
        else:
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)

        if self.path == "/chatbot":
            user_message = data.get("message", "").lower().strip()
            response_text = get_chatbot_response(user_message)

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"response": response_text}).encode())
            return  # Add this return statement to prevent further execution

        elif self.path == "/book_slot":
            slot_id = data.get("id")
            for slot in parking_slots:
                if slot["id"] == slot_id and slot["status"] == "available":
                    slot["status"] = "booked"
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": True, "message": f"Slot {slot_id} booked successfully"}).encode())
                    return

            self.send_response(400)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "message": "Slot is already booked"}).encode())

# Web server code
class WebsiteHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/slots":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(parking_slots).encode())
        elif self.path == "/users":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            with open("data.json", "r") as f:
                self.wfile.write(f.read().encode())
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            with open("regist.html", "r", encoding="utf-8") as file:
                self.wfile.write(file.read().encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/book_slot":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)

            slot_id = data.get("id")
            for slot in parking_slots:
                if slot["id"] == slot_id and slot["status"] == "available":
                    slot["status"] = "booked"
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": True, "message": f"Slot {slot_id} booked successfully"}).encode())
                    return

            self.send_response(400)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "message": "Slot is already booked"}).encode())

# Run server function
def run_server():
    PORT = 8000
    Handler = WebsiteHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving at port {PORT}")
        httpd.serve_forever()

# Initialize the web server and bot
def main():
    update_database_schema()  # Ensure the database schema is up to date
    app = Application.builder().token("7722239853:AAE6HbTS4T2E-bO2noI05SXDRIIbC8N3q7o").build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact)],
            ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, address)],
            START_HOUR: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_hour)],
            END_HOUR: [MessageHandler(filters.TEXT & ~filters.COMMAND, end_hour)],
            CAR_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, car_number)],
            BOOK_SLOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, book_slot)],
        },
        fallbacks=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_other_text)],
    )

    app.add_handler(conv_handler)
    print("Bot is running...")
    app.run_polling()

    def get_chatbot_response(user_message):
        faq_responses = {
        "how does the smart car parking system work": "The Smart Car Parking System uses IoT sensors to detect free slots and allows online booking through Telegram bot and website.",
        "how do i book a parking slot": "You can book a slot by using the Telegram bot or visiting our website.",
        "what are the available slots": f"Currently, {sum(1 for slot in parking_slots if slot['status'] == 'available')} slots are available.",
        "how much does parking cost": "The parking rates depend on the location and time. Please check the pricing on the website.",
        "how can i cancel my parking slot": "You can cancel your slot by visiting the website or contacting customer support.",
        "is there a time limit for parking": "Yes, each parking slot has a maximum time limit of 8 hours. Exceeding this limit may result in additional charges.",
        "what payment methods are available": "You can pay using credit/debit cards, UPI, and digital wallets."
    }

    return faq_responses.get(user_message, "Sorry, I am not sure about that. Please ask something else!")


    return faq_responses.get(user_message, "Sorry, I am not sure about that. Please ask something else!")


# Start the web server and bot
if __name__ == "__main__":
    # Your code goes here

    threading.Thread(target=run_server, daemon=True).start()
    main()