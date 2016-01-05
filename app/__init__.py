from flask import Flask, request, render_template, jsonify
import json
from pymongo import MongoClient
from datetime import datetime, timedelta
import os, sys

app = Flask(__name__)
client = MongoClient()
db = client['test']
posts = db['posts']
queue = db['queue']

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        data = request.json
        _id = posts.insert(request.json)
        uid = data['uid']
        q = queue.find_one({'uid' : uid})
        if q is not None:
            queue.remove({'_id' : q['_id']}) # remove action from queue
            task = q['task']
            print q
        else:
            task = None
        response = {
            "status" : "ok",
            "task" : task #!TODO: send task to node
        }
        return jsonify(response)
    elif request.method == 'GET':
        return render_template('index.html')
    else:
        return None

@app.route('/node/')
def show_nodes():
    return render_template('index.html')   

@app.route('/node/<node_id>')
def show_node_summary(node_id):
    dt = timedelta(hours=1)
    time_a = datetime.now()
    time_b = datetime.now() - dt
    doc_template = {
        "uid" : node_id,
        "time" : {"$lt": time_b, "$gt": time_a} #!TODO search by time frame
    }
    docs = posts.find(doc_template)
    snapshot = [d for d in docs]
    return render_template('node.html', node_id=node_id, snapshot=snapshot)

"""
API Functions
"""
@app.route('/api/update_queue', methods=['GET', 'POST'])
def update_queue():
    if request.method == "POST":
        data = request.form.to_dict()
        if data is not None:
            _id = queue.insert(data)
            status = "ok"
        else:
            status = "bad"
    else:
        status = "awful"
    response = {
        "status" : status
    }
    return jsonify(response)

if __name__ == '__main__':
    app.run()
