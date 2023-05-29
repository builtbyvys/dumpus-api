import orjson
import os
import cryptocode

from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS, cross_origin

# make sure tasks is imported before db
# as env is loaded from tasks (so the celery worker can use it)
from tasks import handle_package
from db import PackageProcessStatus, SavedPackageData, Session

from util import check_discord_link, extract_key_from_discord_link, extract_package_id_from_discord_link, ts_included_in_range

app = Flask(__name__)
CORS(app)

def fetch_package_status(package_id, session):
    status = session.query(PackageProcessStatus).filter_by(package_id=package_id).first()
    if status:
        return {
            'status': 'processing',
            'step': status.step,
        }
    else:
        return {
            'status': 'unknown',
            'message': 'This link has not been analyzed yet.',
        }
    
def fetch_package_data(package_id, auth_upn, session):
    status = session.query(PackageProcessStatus).filter_by(package_id=package_id).first()
    if status and status.step == 'processed':
        result = session.query(SavedPackageData).filter_by(package_id=package_id).first()
        data = cryptocode.decrypt(result.data, auth_upn)
        if result:
            return {
                'status': 'processed',
                'data': data
            }
    else:
        return {
            'status': 'unknown',
            'message': 'This link has not been analyzed yet.',
        }

@app.route('/process', methods=['POST'])
def process_link():
    print(f'processing link')
    # Get link from body
    link = request.json['package_link']
    if not link:
        return jsonify({'error': 'No link provided.'}), 400
    # Check if link is a discord link
    if not check_discord_link(link):
        return jsonify({'error': 'Not a discord link.'}), 400
    # Link to md5
    package_id = extract_package_id_from_discord_link(link)
    print(f'making sure link is not already processed (package_id: {package_id})')
    # Get package status
    session = Session()
    package_stats = fetch_package_status(package_id, session)
    if package_stats['status'] != 'unknown':
        return jsonify({
            'status': package_stats['status'],
            'message': 'This link has already been submitted.'
        })
    print(f'order taken, started processing (package_id: {package_id})')
    package_process_status = PackageProcessStatus(package_id=package_id, step='locked', progress=0)
    session.add(package_process_status)
    session.commit()
    session.close()
    # Process the link
    handle_package.apply_async(args=[package_id, link])
    # Send a successful response
    return jsonify({'success': 'Started processing your link.'}), 200

@app.route('/process/<package_id>/status', methods=['GET'])
def get_package_status(package_id):
    session = Session()
    package_status = fetch_package_status(package_id, session)
    session.close()
    return jsonify(package_status), 200

@app.route('/process/<package_id>/data', methods=['GET'])
def get_package_data(package_id):

    # Get authorization bearer token
    auth_header = request.headers.get('Authorization')

    # Check if token is present
    if not auth_header:
        return jsonify({'error': 'No authorization token provided.'}), 400
    
    # remove bearer
    auth_upn = auth_header.split(' ')[1]
    
    session = Session()
    package_status = fetch_package_data(package_id, auth_upn, session)
    session.close()
    return jsonify(package_status), 200

@app.route('/health', methods=['GET'])
def health_check():
    return '', 200

@app.errorhandler(404)
def page_not_found(e):
    return jsonify({'error': 'Route not found.'}), 404

@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({'error': 'Internal server error.'}), 500
