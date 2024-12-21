from flask import Flask, jsonify, request
from pymongo import MongoClient
import logging
from datetime import datetime

app = Flask(__name__)

client = MongoClient("mongodb://localhost:27017/")
db = client["db"]
users = db["users"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/register', methods=['POST'])
def register_user():
    login = request.get_json()['login']
    name = request.get_json()['name']

    logger.warn("Register user " + str(login))

    user = users.find_one({"login": login}, {'_id': 0})
    if user is None:
        user = {
            "login": login, 
            "name": name, 
            "last_timestamp": 0,
            "limit": 5,
            "period": 1,
            "channels": [],
            "feeds": []
        }
        users.insert_one(user)
        user = users.find_one({"login": login}, {'_id': 0})
        return jsonify({"ok": user}), 201
    return jsonify({"error": user}), 400


@app.route('/limit', methods=['GET'])
def get_limit():
    login = request.get_json()['login']
    user = users.find_one({"login": login})
    if user is None:
        return {"error": f"User {login} not found"}, 404
    limit = user['limit']
    return {"ok": limit}, 200


@app.route('/limit', methods=['PUT'])
def set_limit():
    data = request.get_json()
    login = data['login']
    limit = data['limit']
    user = users.find_one({"login": login})
    if user is None:
        return {"error": f"User {login} not found"}, 404
    users.update_one(
        {'login': login},
        {'$set': {'limit': limit}}
    )
    return {"ok": limit}, 200


@app.route('/period', methods=['GET'])
def get_period():
    login = request.get_json()['login']
    user = users.find_one({"login": login})
    if user is None:
        return {"error": f"User {login} not found"}, 404
    period = user['period']
    return {"ok": period}, 200


@app.route('/period', methods=['PUT'])
def set_pariod():
    data = request.get_json()
    login = data['login']
    period = data['period']
    user = users.find_one({"login": login})
    if user is None:
        return {"error": f"User {login} not found"}, 404
    users.update_one(
        {'login': login},
        {'$set': {'period': period}}
    )
    return {"ok": period}, 200


@app.route('/channels', methods=['GET'])
def get_channels():
    login = request.get_json()['login']
    user = users.find_one({"login": login})
    if user is None:
        return {"error": f"User {login} not found"}, 404
    channels = user['channels']
    return {"ok": channels}, 200


@app.route('/feeds', methods=['GET'])
def get_feeds():
    login = request.get_json()['login']
    user = users.find_one({"login": login})
    if user is None:
        return {"error": f"User {login} not found"}, 404
    feeds = user['feeds']
    return {"ok": feeds}, 200


@app.route('/subscribe', methods=['PUT'])
def subscribe():
    data = request.get_json()

    login = data['login']
    user = users.find_one({"login": login})
    if user is None:
        return {'error': f'User {user} not found'}, 404
    
    if 'channel' in data:
        channel = data['channel']
        if channel in user['channels']:
            return {'error': f'User {login} has already subscribed to channel {channel}'}
        users.update_one(
            {'login': login},
            {'$push': {'channels': channel}}
        )
        return {"ok": channel}, 200
    if 'feed' in data:
        feed = data['feed']
        if feed in user['feeds']:
            return {'error': f'User {login}  has already subscribed to feed {feed}'}
        users.update_one(
            {'login': login},
            {'$push': {'feeds': feed}}
        )
        return {"ok": feed}, 200
    return {'error': 'Bad request'}, 404


@app.route('/unsubscribe', methods=['PUT'])
def unsubscribe():
    data = request.get_json()

    login = data['login']
    user = users.find_one({"login": login})
    if user is None:
        return {'error': f'User {login} not found'}, 404

    if 'channel' in data:
        channel = data['channel']    
        if channel not in user['channels']:
            return {'error': f'User {login} not subscribed to channel {channel}'}
        users.update_one(
            {'login': login},
            {'$pull': {'channels': channel}}
        )
        return {"ok": channel}, 200
    if 'feed' in data:
        feed = data['feed']
        if feed not in user['feeds']:
            return {'error': f'User {login} not subscribed to feed {feed}'}
        users.update_one(
            {'login': login},
            {'$pull': {'feeds': feed}}
        )
        return {"ok": feed}, 200
    return {'error': 'Bad request'}, 404


@app.route('/user', methods=['GET'])
def get_user():
    login = request.get_json()['login']
    user = users.find_one({"login": login})
    if user is None:
        return {'error': f'User {login} not found'}, 404
    return {"ok": login}, 200


@app.route('/drop', methods=['DELETE'])
def drop_user():
    login = request.get_json()['login']
    if users.delete_one({'login': login}).deleted_count:
        return {'ok': login}, 201
    return {'error': f'User {login} not found'}, 404


if __name__ == '__main__':
    app.run(debug=True, host="127.0.0.1", port=5000)
