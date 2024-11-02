from flask import Flask, jsonify, request
from pymongo import MongoClient
import logging

app = Flask(__name__)

client = MongoClient("mongodb://mongo:27017/")
db = client["db"]
users = db["users"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/register', methods=['POST'])
def register_user():
    user_id = request.get_json()['user_id']
    user = users.find_one({"user_id": user_id}, {'_id': 0})
    if user is None:
        user = {"user_id": user_id, "channels": []}
        users.insert_one(user)
        user = users.find_one({"user_id": user_id}, {'_id': 0})
        return jsonify({"ok": user}), 201
    return jsonify({"error": user}), 400


@app.route('/channels', methods=['GET'])
def get_channels():
    user_id = request.get_json()['user_id']
    user = users.find_one({"user_id": user_id})
    if user is None:
        return {"error": f"User {user_id} not found"}, 404
    channels = user['channels']
    return {"ok": channels}, 200


@app.route('/subscribe', methods=['PUT'])
def subscribe():
    data = request.get_json()

    user_id = data['user_id']
    channel_id = data['channel_id']

    user = users.find_one({"user_id": user_id})
    if user is None:
        return {'error': f'User {user_id} not found'}, 404
    if channel_id in user['channels']:
        return {'error': f'User {user_id} has already subscribed to channel {channel_id}'}
    
    users.update_one(
        {'user_id': user_id},
        {'$push': {'channels': channel_id}}
    )
    return {"ok": channel_id}, 200


@app.route('/unsubscribe', methods=['PUT'])
def unsubscribe():
    data = request.get_json()

    user_id = data['user_id']
    channel_id = data['channel_id']

    user = users.find_one({"user_id": user_id})
    if user is None:
        return {'error': f'User {user_id} not found'}, 404
    if channel_id not in user['channels']:
        return {'error': f'User {user_id} not subscribed to channel {channel_id}'}
    
    users.update_one(
        {'user_id': user_id},
        {'$pull': {'channels': channel_id}}
    )
    return {"ok": channel_id}, 200


@app.route('/drop', methods=['DELETE'])
def drop_user():
    user_id = request.get_json()['user_id']
    if users.delete_one({'user_id': user_id}).deleted_count:
        return {'ok': user_id}, 201
    return {'error': f'User {user_id} not found'}, 404


if __name__ == '__main__':
    app.run(debug=True, host="127.0.0.1", port=5000)
