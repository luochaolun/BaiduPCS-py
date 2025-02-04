import os
import json
import requests
import argparse
import hashlib
import time

CONFIG_FILE = "config.json"
USER_AGENT = "netdisk;2.2.51.6;netdisk;10.0.63;PC;android-android"

def save_bduss(bduss):
    config = {"bduss": bduss}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    print("Successfully logged in.")

def load_bduss():
    if not os.path.exists(CONFIG_FILE):
        raise Exception("No BDUSS found. Please login first.")
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    return config["bduss"]

def get_user_info(bduss):
    headers = {"User-Agent": USER_AGENT}
    cookies = {"BDUSS": bduss}
    response = requests.get("https://pan.baidu.com/rest/2.0/xpan/nas?method=uinfo", headers=headers, cookies=cookies)
    if response.status_code != 200:
        raise Exception("Failed to get user info: status code {}".format(response.status_code))
    user_info = response.json()
    print("Debug: Response JSON:", user_info)
    if 'baidu_name' not in user_info:
        raise Exception("Error: 'baidu_name' key not found in the response. Please check the response structure.")
    return user_info

def list_directory(bduss, path):
    headers = {"User-Agent": USER_AGENT}
    cookies = {"BDUSS": bduss}
    params = {
        "method": "list",
        "dir": path,
        "order": "name",
        "start": 0,
        "limit": 100
    }
    response = requests.get("https://pan.baidu.com/rest/2.0/xpan/file", headers=headers, cookies=cookies, params=params)
    if response.status_code != 200:
        print("Debug: Response URL:", response.url)
        print("Debug: Response status code:", response.status_code)
        print("Debug: Response content:", response.text)
        raise Exception("Failed to list directory: status code {}".format(response.status_code))
    items = response.json()
    print("Debug: Directory contents:", items)
    if 'list' not in items:
        raise Exception("Error: 'list' key not found in the response.")
    return items["list"]

def generate_sign(uid, bduss):
    sha1_bduss = hashlib.sha1(bduss.encode('utf-8')).hexdigest()
    sha1_combined = hashlib.sha1((sha1_bduss + str(uid) + "ebrcUYiuXZa2XGu7KIYKxUrqfnOfpDF").encode('utf-8')).hexdigest()
    return sha1_combined

def locate_pan_api_download(bduss, fs_ids):
    headers = {"User-Agent": USER_AGENT}
    cookies = {"BDUSS": bduss}
    params = {
        "method": "locatedownload",
        "app_id": "250528",
        "fs_ids": json.dumps(fs_ids),
        "ver": "2.1"
    }
    response = requests.get("https://pan.baidu.com/rest/2.0/xpan/file", headers=headers, cookies=cookies, params=params)
    if response.status_code != 200:
        raise Exception("Failed to locate pan API download: status code {}".format(response.status_code))
    download_info = response.json()
    print("Debug: locate_pan_api_download response:", download_info)
    if 'dlink' not in download_info:
        raise Exception("Error: 'dlink' key not found in the response.")
    return download_info['dlink']

def locate_file(bduss, path, uid):
    headers = {"User-Agent": USER_AGENT}
    cookies = {"BDUSS": bduss}
    
    # Get the file metadata to retrieve the fs_id
    dir_path = os.path.dirname(path)
    file_name = os.path.basename(path)
    files = list_directory(bduss, dir_path)
    
    # Find the file with the exact name
    file_info = next((f for f in files if f["path"] == path or f["server_filename"] == file_name), None)
    if not file_info:
        raise Exception(f"File '{path}' not found.")
    
    fs_id = file_info["fs_id"]
    timestamp = int(time.time())
    devuid = hashlib.md5(bduss.encode('utf-8')).hexdigest().upper()
    sign = generate_sign(uid, bduss)
    
    # Use the fs_id to locate the download URL
    locate_params = {
        "method": "locatedownload",
        "app_id": "250528",
        "path": path,
        "ver": "4.0",
        "time": timestamp,
        "rand": sign,
        "devuid": devuid,
        "cuid": devuid
    }
    
    retry_attempts = 3
    for attempt in range(retry_attempts):
        response = requests.get("https://d.pcs.baidu.com/rest/2.0/pcs/file", headers=headers, cookies=cookies, params=locate_params)
        if response.status_code == 200:
            try:
                url_info = response.json()
                print("Debug: filemetas response:", url_info)
                if "urls" not in url_info:
                    if url_info.get('errno') == 9019:
                        print("Verification required. Please complete any necessary verification steps on the Baidu website.")
                        break
                    raise Exception("'urls' key not found in the response.")
                return [url["url"] for url in url_info["urls"]]
            except json.JSONDecodeError as e:
                print("Debug: JSON decode error:", e)
                print("Debug: Response text:", response.text)
                raise Exception("Failed to decode JSON response.")
        elif response.status_code == 500:
            print(f"Debug: Internal server error on attempt {attempt + 1}, retrying...")
            time.sleep(1)
        else:
            print("Debug: Response URL:", response.url)
            print("Debug: Response status code:", response.status_code)
            print("Debug: Response content:", response.text)
            raise Exception("Failed to locate file: status code {}".format(response.status_code))
    
    raise Exception("Failed to locate file after multiple attempts.")

def main():
    parser = argparse.ArgumentParser(description="BaiduPCS-Go in Python")
    parser.add_argument("command", choices=["login", "who", "ls", "locate"], help="Command to execute")
    parser.add_argument("--bduss", help="BDUSS for login")
    parser.add_argument("--path", help="Path for ls or locate command")
    parser.add_argument("--from-pan", action="store_true", help="Locate from pan")

    args = parser.parse_args()

    if args.command == "login":
        if not args.bduss:
            print("Usage: main.py login --bduss <BDUSS>")
            return
        save_bduss(args.bduss)

    elif args.command == "who":
        try:
            bduss = load_bduss()
            user_info = get_user_info(bduss)
            print(f"Current user: {user_info['baidu_name']} (UID: {user_info['uk']})")
        except Exception as e:
            print(f"Error: {e}")

    elif args.command == "ls":
        if not args.path:
            print("Usage: main.py ls --path <directory>")
            return
        try:
            bduss = load_bduss()
            items = list_directory(bduss, args.path)
            for item in items:
                print(f"{item['isdir']}\t{item['path']}")
        except Exception as e:
            print(f"Error: {e}")

    elif args.command == "locate":
        if not args.path:
            print("Usage: main.py locate --path <file>")
            return
        try:
            bduss = load_bduss()
            user_info = get_user_info(bduss)
            uid = user_info['uk']
            if args.from_pan:
                files = list_directory(bduss, os.path.dirname(args.path))
                fs_ids = [f["fs_id"] for f in files if f["path"] == args.path or f["server_filename"] == os.path.basename(args.path)]
                if not fs_ids:
                    raise Exception(f"File '{args.path}' not found.")
                urls = locate_pan_api_download(bduss, fs_ids)
            else:
                urls = locate_file(bduss, args.path, uid)
            for url in urls:
                print(url)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
