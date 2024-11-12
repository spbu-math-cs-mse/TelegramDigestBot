from flask import Flask, jsonify, request
from pymongo import MongoClient
import logging
from datetime import datetime

app = Flask(__name__)

client = MongoClient("mongodb://mongo:27017/")
db = client["db"]
users = db["users"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/register', methods=['POST'])
def register_user():
    login = request.get_json()['login']
    name = request.get_json()['name']

    user = users.find_one({"login": login}, {'_id': 0})
    if user is None:
        user = {
            "login": login, 
            "name": name, 
            "last_timestamp": 0,
            "channels": []
        }
        users.insert_one(user)
        user = users.find_one({"login": login}, {'_id': 0})
        return jsonify({"ok": user}), 201
    return jsonify({"error": user}), 400


@app.route('/channels', methods=['GET'])
def get_channels():
    login = request.get_json()['login']
    user = users.find_one({"login": login})
    if user is None:
        return {"error": f"User {login} not found"}, 404
    channels = user['channels']
    return {"ok": channels}, 200


@app.route('/subscribe', methods=['PUT'])
def subscribe():
    data = request.get_json()

    user_login = data['user_login']
    channel_login = data['channel_login']

    user = users.find_one({"login": user_login})
    if user is None:
        return {'error': f'User {user_login} not found'}, 404
    if channel_login in user['channels']:
        return {'error': f'User {user_login} has already subscribed to channel {channel_login}'}
    
    users.update_one(
        {'login': user_login},
        {'$push': {'channels': channel_login}}
    )

    return {"ok": channel_login}, 200


@app.route('/unsubscribe', methods=['PUT'])
def unsubscribe():
    data = request.get_json()

    user_login = data['user']
    channel_login = data['channel']

    user = users.find_one({"login": user_login})
    if user is None:
        return {'error': f'User {user_login} not found'}, 404
    if channel_login not in user['channels']:
        return {'error': f'User {user_login} not subscribed to channel {channel_login}'}
    
    users.update_one(
        {'user_id': user_login},
        {'$pull': {'channels': channel_login}}
    )

    return {"ok": channel_login}, 200


@app.route('/drop', methods=['DELETE'])
def drop_user():
    login = request.get_json()['login']
    if users.delete_one({'login': login}).deleted_count:
        return {'ok': login}, 201
    return {'error': f'User {login} not found'}, 404


if __name__ == '__main__':
    app.run(debug=True, host="127.0.0.1", port=5000)
