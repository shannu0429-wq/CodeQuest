import requests

BOT_TOKEN = "8860530064:AAGTyJdxP5Ted5OKsbirGmMQKLFqePB6ajA"
CHAT_ID = "-5307916387"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }
    response = requests.post(
        url,
        data=data
    )
    print("Telegram status:", response.status_code)
    print("Telegram response:", response.text)
    return response

if __name__ == "__main__":
    send_telegram_message(
        """📢 CodeQuest

A new question has been added!

🚀 Login to CodeQuest and try it."""
    )
