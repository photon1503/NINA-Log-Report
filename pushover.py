import http.client
import urllib
import json

class PushoverClient:
  
    
    def __init__(self, token, user_key):
        self.token = token
        self.user_key = user_key
   
        self.conn = http.client.HTTPSConnection("api.pushover.net:443")

    def send_message(self, message):
        if len(message) > 1024:
            messages = [message[i:i+1024] for i in range(0, len(message), 1024)]
            for msg in messages:
                self.send_message(msg)
        self.conn.request("POST", "/1/messages.json",
                          urllib.parse.urlencode({
                              "token": self.token,
                              "user": self.user_key,
                              "message": message,
                          }), {"Content-type": "application/x-www-form-urlencoded"})
        response = self.conn.getresponse()
        return response.read()

# Example usage:
# pushover = PushoverClient("APP_TOKEN", "USER_KEY")
# response = pushover.send_message("hello world")
# print(response)