# -*- coding: utf-8 -*-
"""
Prima TV Provider - LIVE + CATCHUP
Based on waladir/plugin.video.primaplus for catchup API
License: AGPL v.3
"""

import requests
import re
import json
import time
import os
from datetime import datetime as dt, timedelta as td, timezone as tz

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

try:
    import xbmc
    import xbmcaddon
    import xbmcvfs
    _addon = xbmcaddon.Addon()
    _profile = xbmcvfs.translatePath(_addon.getAddonInfo('profile'))
    def log(msg):
        xbmc.log(f'[LiveTV CZ/SK] Prima: {msg}', xbmc.LOGINFO)
    def log_error(msg):
        xbmc.log(f'[LiveTV CZ/SK] Prima ERROR: {msg}', xbmc.LOGERROR)
except:
    _addon = None
    _profile = None
    def log(msg):
        print(f'[LiveTV CZ/SK] Prima: {msg}')
    def log_error(msg):
        print(f'[LiveTV CZ/SK] Prima ERROR: {msg}')

PROXY_BASE = "http://p.6f.sk"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36'
}
CHANNELS = ['prima', 'love', 'krimi', 'max', 'cool', 'zoom', 'star', 'show']

# Prima+ channel IDs for catchup (from gateway-api)
PRIMA_CHANNEL_IDS = {
    'prima': 'prima',
    'primalove': 'love', 
    'primakrimi': 'krimi',
    'primamax': 'max',
    'primacool': 'cool',
    'primazoom': 'zoom',
    'primastar': 'star',
    'primashow': 'show',
    'cnnprimanews': 'cnn'
}


def get_prima_settings():
    """Get Prima login settings from addon"""
    if _addon:
        email = _addon.getSetting('prima_email') or ''
        password = _addon.getSetting('prima_password') or ''
        log(f"Settings loaded - email: {email[:3]}*** (len={len(email)})")
        return email, password
    return '', ''


def get_token_file():
    """Get path to token cache file"""
    if _profile:
        return os.path.join(_profile, 'prima_token.json')
    return None


def save_token(token_data):
    """Save token to cache file"""
    token_file = get_token_file()
    if token_file:
        try:
            with open(token_file, 'w', encoding='utf-8') as f:
                json.dump(token_data, f)
            log(f"Token saved to {token_file}")
        except Exception as e:
            log_error(f"Failed to save token: {e}")


def load_token():
    """Load token from cache file"""
    token_file = get_token_file()
    if token_file and os.path.exists(token_file):
        try:
            with open(token_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                log(f"Token loaded from cache, valid_to: {data.get('valid_to', 'unknown')}")
                return data
        except Exception as e:
            log_error(f"Failed to load token: {e}")
    return None


def get_prima_token():
    """
    Get Prima+ access token for catchup
    Requires registration at iprima.cz (free account works for some content)
    """
    log("Getting Prima+ token...")
    
    # Check cached token
    cached = load_token()
    if cached and 'token' in cached and 'valid_to' in cached:
        if cached['valid_to'] > int(time.time()):
            log("Using cached token (still valid)")
            return cached['token']
        else:
            log("Cached token expired")
    
    # Get login credentials
    email, password = get_prima_settings()
    if not email or not password:
        log_error("No Prima+ credentials configured!")
        return None
    
    try:
        log(f"Logging in to Prima+ as {email[:3]}***")
        headers = {'User-Agent': HEADERS['User-Agent']}
        response = requests.post(
            'https://ucet.iprima.cz/api/session/create',
            json={
                'email': email,
                'password': password,
                'deviceName': 'Kodi LiveTV CZ/SK'
            },
            headers=headers,
            timeout=15
        )
        log(f"Login response status: {response.status_code}")
        data = response.json()
        
        if 'accessToken' in data:
            token = data['accessToken']['value']
            token_data = {
                'token': token,
                'valid_to': int(time.time()) + 7*60*60  # 7 hours validity
            }
            save_token(token_data)
            log("Login successful, token obtained!")
            return token
        else:
            log_error(f"Login failed: {data}")
    except Exception as e:
        log_error(f"Token error: {e}")
    
    return None


def get_cnn_stream():
    """Get CNN Prima News stream (no login required)"""
    try:
        session = requests.Session()
        headers = {}
        headers.update(HEADERS)
        response = session.get(
            'https://api.play-backend.iprima.cz/api/v1/products/id-p650443/play',
            headers=headers,
            timeout=15
        )
        data = response.json()
        if 'streamInfos' in data and data['streamInfos']:
            stream = data['streamInfos'][0]['url']
            stream = stream.replace("_lq", "")
            return {
                'url': stream,
                'manifest_type': 'hls',
                'headers': HEADERS
            }
    except Exception as e:
        return {'error': str(e)}
    return None


def get_live_stream(channel_id):
    """Get live stream URL for Prima channels"""
    # CNN Prima News has special handling (no proxy needed)
    if channel_id == 'cnn' or channel_id == 'cnnprimanews':
        return get_cnn_stream()
    
    # Map channel names
    channel_map = {
        'prima': 'prima',
        'primalove': 'love',
        'primakrimi': 'krimi',
        'primamax': 'max',
        'primacool': 'cool',
        'primazoom': 'zoom',
        'primastar': 'star',
        'primashow': 'show'
    }
    
    channel = channel_map.get(channel_id, channel_id)
    
    if channel not in CHANNELS:
        return None
    
    try:
        session = requests.Session()
        headers = {}
        headers.update(HEADERS)
        
        # Load proxy index to keep it alive
        try:
            response = session.get(PROXY_BASE, headers=headers, timeout=10)
            content = response.text
            scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', content)
            for src in scripts:
                if src.startswith("//"):
                    src = "http:" + src
                try:
                    session.get(src, headers=headers, timeout=5)
                except:
                    pass
        except:
            pass
        
        return {
            'url': PROXY_BASE + "/iprima.php?ch=" + channel,
            'manifest_type': 'hls',
            'headers': HEADERS
        }
    except Exception as e:
        return {'error': str(e)}
    
    return None


def get_epg_channels():
    """Get list of Prima channels with EPG IDs for catchup"""
    log("Getting EPG channels list...")
    token = get_prima_token()
    if not token:
        log_error("No token for EPG channels")
        return None
    
    try:
        headers = {
            'Authorization': f'Bearer {token}',
            'X-OTT-Access-Token': token,
            'X-OTT-CDN-Url-Type': 'WEB',
            'User-Agent': HEADERS['User-Agent'],
            'Accept': 'application/json; charset=utf-8',
            'Content-type': 'application/json;charset=UTF-8'
        }
        
        post_data = {
            'id': '1',
            'jsonrpc': '2.0',
            'method': 'epg.channel.list',
            'params': {}
        }
        
        response = requests.post(
            'https://gateway-api.prod.iprima.cz/json-rpc/',
            json=post_data,
            headers=headers,
            timeout=15
        )
        log(f"EPG channels response status: {response.status_code}")
        data = response.json()
        
        if 'result' in data and 'data' in data['result']:
            channels = data['result']['data']
            log(f"Found {len(channels)} EPG channels")
            for ch in channels:
                log(f"  Channel: id={ch.get('id')}, title={ch.get('title')}")
            return channels
        else:
            log_error(f"EPG channels response: {data}")
    except Exception as e:
        log_error(f"EPG channels error: {e}")
    
    return None


def get_epg_program(channel_id, day_offset=0):
    """
    Get EPG program for a Prima channel
    day_offset: 0 = today, -1 = yesterday, etc.
    """
    token = get_prima_token()
    if not token:
        return None
    
    try:
        target_date = dt.now() + td(days=day_offset)
        date_str = target_date.strftime('%Y-%m-%d')
        
        log(f"Getting EPG for channel {channel_id}, date {date_str}")
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-OTT-Access-Token': token,
            'X-OTT-CDN-Url-Type': 'WEB',
            'User-Agent': HEADERS['User-Agent'],
            'Accept': 'application/json; charset=utf-8',
            'Content-type': 'application/json;charset=UTF-8'
        }
        
        # Use epg.program.bulk.list with correct format from waladir's addon
        post_data = {
            'id': 'web-1',
            'jsonrpc': '2.0',
            'method': 'epg.program.bulk.list',
            'params': {
                'date': {'date': date_str},  # Object with date key
                'channelIds': [channel_id]   # Array of channel IDs
            }
        }
        
        response = requests.post(
            'https://gateway-api.prod.iprima.cz/json-rpc/',
            json=post_data,
            headers=headers,
            timeout=15
        )
        data = response.json()
        
        if 'result' in data and 'data' in data['result'] and len(data['result']['data']) > 0:
            # Response is array of channels, each with 'items'
            channel_data = data['result']['data'][0]
            if 'items' in channel_data:
                programs = channel_data['items']
                log(f"Found {len(programs)} programs for {date_str}")
                return programs
            else:
                log(f"No items in channel data: {channel_data}")
        else:
            log(f"No programs found: {data}")
    except Exception as e:
        log_error(f"EPG program error: {e}")
    
    return None


def find_program_by_timestamp(prima_channel_id, utc_timestamp):
    """
    Find a program in Prima archive by UTC timestamp
    Returns the playId if found
    """
    log(f"Finding program for channel={prima_channel_id}, utc={utc_timestamp}")
    
    # Convert UTC timestamp to LOCAL time (CET/CEST - Prague timezone)
    # Prima API returns times in local Czech time, not UTC
    utc_time = dt.utcfromtimestamp(int(utc_timestamp))
    # Add 1 hour for CET (or 2 hours for CEST in summer)
    # For simplicity, use 1 hour offset (winter time)
    # TODO: proper timezone handling
    program_time = utc_time + td(hours=1)  # UTC -> CET
    log(f"Looking for program at UTC time: {utc_time}, local CET time: {program_time}")
    
    # Search in the past 7 days
    for day_offset in range(0, -8, -1):
        programs = get_epg_program(prima_channel_id, day_offset)
        if not programs:
            log(f"No programs for day_offset={day_offset}")
            continue
        
        log(f"Checking {len(programs)} programs for day_offset={day_offset}")
        
        # Log first program to see structure
        if programs and day_offset == 0:
            log(f"First program structure: {list(programs[0].keys()) if isinstance(programs[0], dict) else type(programs[0])}")
        
        for program in programs:
            try:
                # Handle both dict and other types
                if not isinstance(program, dict):
                    log_error(f"Program is not a dict: {type(program)}")
                    continue
                
                start_str = program.get('programStartTime') or program.get('startTime') or ''
                end_str = program.get('programEndTime') or program.get('endTime') or ''
                title = program.get('title', 'Unknown')
                
                if not start_str or not end_str:
                    log(f"Program missing times: {title}, keys={list(program.keys())}")
                    continue
                
                start_str = start_str[:19]
                end_str = end_str[:19]
                
                start_time = dt.strptime(start_str, '%Y-%m-%dT%H:%M:%S')
                end_time = dt.strptime(end_str, '%Y-%m-%dT%H:%M:%S')
                
                # Check if the timestamp falls within this program
                if start_time <= program_time <= end_time:
                    log(f"MATCH! Program: {title}, start={start_time}, end={end_time}")
                    is_playable = program.get('isPlayable', False)
                    play_id = program.get('playId') or program.get('id')
                    log(f"  isPlayable={is_playable}, playId={play_id}")
                    
                    if is_playable and play_id:
                        return play_id
                    else:
                        log(f"  Program not playable or no playId")
                        return None
            except Exception as e:
                log_error(f"Error checking program: {e}, program keys: {list(program.keys()) if isinstance(program, dict) else 'N/A'}")
                continue
    
    log("No matching program found in archive")
    return None


def get_catchup_stream(channel_id, utc_timestamp):
    """
    Get catchup/archive stream for Prima channels
    Requires Prima+ account (free registration works for some content)
    
    Args:
        channel_id: Channel identifier (prima, primalove, etc.)
        utc_timestamp: Unix timestamp of the program start time
    
    Returns:
        dict with 'url', 'manifest_type', 'headers' or 'error'
    """
    log(f"=== CATCHUP REQUEST: channel={channel_id}, utc={utc_timestamp} ===")
    
    token = get_prima_token()
    if not token:
        log_error("No token available!")
        return {
            'error': 'Prima+ catchup vyžaduje přihlášení. Nastavte email a heslo v nastaveních doplňku.'
        }
    
    log("Token obtained, getting channel list...")
    
    # First, get channels list to find correct Prima channel ID
    channels = get_epg_channels()
    if not channels:
        log_error("Could not get channel list")
        return {'error': 'Nelze získat seznam kanálů Prima'}
    
    # Map our channel_id to Prima's internal channel_id
    prima_channel_id = None
    
    # Try to find by matching name
    channel_name_map = {
        'prima': ['prima', 'tv prima'],
        'primacool': ['cool', 'prima cool'],
        'primamax': ['max', 'prima max'],
        'primakrimi': ['krimi', 'prima krimi'],
        'primalove': ['love', 'prima love'],
        'primazoom': ['zoom', 'prima zoom'],
        'primastar': ['star', 'prima star'],
        'primashow': ['show', 'prima show'],
        'cnnprimanews': ['cnn', 'cnn prima']
    }
    
    search_names = channel_name_map.get(channel_id, [channel_id])
    log(f"Looking for channel matching: {search_names}")
    
    for ch in channels:
        ch_title = ch.get('title', '').lower()
        ch_id = ch.get('id', '')
        
        for name in search_names:
            if name.lower() in ch_title:
                prima_channel_id = ch_id
                log(f"Found match: {ch_title} -> {ch_id}")
                break
        if prima_channel_id:
            break
    
    if not prima_channel_id:
        log_error(f"Channel not found: {channel_id}")
        return {'error': f'Kanál nenalezen: {channel_id}'}
    
    log(f"Using Prima channel ID: {prima_channel_id}")
    
    # Find the program playId by timestamp
    play_id = find_program_by_timestamp(prima_channel_id, utc_timestamp)
    if not play_id:
        log_error("Program not found in archive")
        return {'error': 'Program nebyl nalezen v archivu Prima+'}
    
    log(f"Found playId: {play_id}")
    
    # Get the stream URL using the playId
    try:
        headers = {
            'Authorization': f'Bearer {token}',
            'X-OTT-Access-Token': token,
            'X-OTT-CDN-Url-Type': 'WEB',
            'User-Agent': HEADERS['User-Agent'],
            'Accept': 'application/json; charset=utf-8',
            'Content-type': 'application/json;charset=UTF-8'
        }
        
        play_url = f'https://api.play-backend.iprima.cz/api/v1/products/id-{play_id}/play'
        log(f"Requesting stream from: {play_url}")
        
        response = requests.get(play_url, headers=headers, timeout=15)
        log(f"Stream response status: {response.status_code}")
        data = response.json()
        
        if 'streamInfos' in data and data['streamInfos']:
            log(f"Found {len(data['streamInfos'])} stream(s)")
            
            # Prefer HLS stream
            stream_url = None
            for stream in data['streamInfos']:
                stream_type = stream.get('type', 'unknown')
                stream_url_temp = stream.get('url', '')
                log(f"  Stream: type={stream_type}, url={stream_url_temp[:50]}...")
                
                if stream_type == 'HLS' and stream_url_temp:
                    stream_url = stream_url_temp
                    break
            
            if not stream_url and data['streamInfos']:
                stream_url = data['streamInfos'][0].get('url')
            
            if stream_url:
                # Remove low quality suffix if present
                stream_url = stream_url.replace('_lq', '')
                log(f"SUCCESS! Stream URL: {stream_url[:80]}...")
                
                return {
                    'url': stream_url,
                    'manifest_type': 'hls',
                    'headers': HEADERS
                }
        
        # Check for errors
        log_error(f"No streams in response: {data}")
        if 'error' in data:
            return {'error': f"Prima+ error: {data['error']}"}
            
    except Exception as e:
        log_error(f"Stream request error: {e}")
        return {'error': f'Chyba při získávání streamu: {str(e)}'}
    
    return {'error': 'Stream nenalezen'}
