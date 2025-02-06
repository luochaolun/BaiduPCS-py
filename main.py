import os
import json
import requests
import argparse
import hashlib
import urllib.parse
import time
import random
import string
import subprocess

CONFIG_FILE = "config.json"
USER_AGENT = "netdisk;P2SP;3.0.0.8;netdisk;11.12.3;ANG-AN00;android-android;10.0;JSbridge4.4.0;jointBridge;1.1.0;"

class BaiduBase:
    def __init__(self, uid, name):
        self.uid = uid
        self.name = name

class Baidu:
    def __init__(self, uid, name, bduss, workdir="/"):
        self.base = BaiduBase(uid, name)
        self.bduss = bduss
        self.workdir = workdir

def random_string(length):
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for i in range(length))

def tieba_client_signature(post_data):
    if not post_data:
        post_data = {}

    if "sign" in post_data:
        del post_data["sign"]

    bduss = post_data.get("BDUSS", "")
    model = random_string(10)
    phone_imei = hashlib.md5((model + "_" + bduss).encode()).hexdigest()

    post_data["_client_type"] = "2"
    post_data["_client_version"] = "7.0.0.0"
    post_data["_phone_imei"] = phone_imei
    post_data["from"] = "mini_ad_wandoujia"
    post_data["model"] = model

    m = hashlib.md5()
    m.update((bduss + "_" + post_data["_client_version"] + "_" + post_data["_phone_imei"] + "_" + post_data["from"]).encode())
    post_data["cuid"] = m.hexdigest().upper() + "|" + phone_imei[::-1]

    keys = sorted(post_data.keys())
    m = hashlib.md5()
    for key in keys:
        m.update((key + "=" + post_data[key]).encode())
    m.update("tiebaclient!!!".encode())

    post_data["sign"] = m.hexdigest().upper()

def new_user_info_by_bduss(bduss):
    timestamp = str(int(time.time()))
    post_data = {
        "bdusstoken": bduss + "|null",
        "channel_id": "",
        "channel_uid": "",
        "stErrorNums": "0",
        "subapp_type": "mini",
        "timestamp": timestamp + "922",
    }
    tieba_client_signature(post_data)

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": "ka=open",
        "net": "1",
        "User-Agent": "bdtb for Android 6.9.2.1",
        "client_logid": timestamp + "416",
        "Connection": "Keep-Alive",
    }

    response = requests.post("http://tieba.baidu.com/c/s/login", data=post_data, headers=headers)

    if response.status_code != 200:
        raise Exception("Failed to get user info")

    data = response.json()
    if data.get("error_code") != "0":
        raise Exception(f"Error code: {data.get('error_code')}, message: {data.get('error_msg')}")

    user_info = data["user"]
    return Baidu(
        uid=int(user_info["id"]),
        name=user_info["name"],
        bduss=bduss
    )

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
    return new_user_info_by_bduss(bduss)

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
        raise Exception("Failed to list directory: status code {}".format(response.status_code))
    items = response.json()
    if 'list' not in items:
        raise Exception("Error: 'list' key not found in the response.")
    return items["list"]

class LocateDownloadSign:
    def __init__(self, uid, bduss):
        self.time = int(time.time())
        self.dev_uid = self.dev_uid(bduss)
        self.sign(uid, bduss)

    def sign(self, uid, bduss):
        rand_sha1 = hashlib.sha1()
        bduss_sha1 = hashlib.sha1()
        bduss_sha1.update(bduss.encode())
        sha1_res_hex = bduss_sha1.hexdigest()
        rand_sha1.update(sha1_res_hex.encode())
        rand_sha1.update(str(uid).encode())
        rand_sha1.update(b'\x65\x62\x72\x63\x55\x59\x69\x75\x78\x61\x5a\x76\x32\x58\x47\x75\x37\x4b\x49\x59\x4b\x78\x55\x72\x71\x66\x6e\x4f\x66\x70\x44\x46')
        rand_sha1.update(str(self.time).encode())
        rand_sha1.update(self.dev_uid.encode())
        self.rand = rand_sha1.hexdigest()

    def dev_uid(self, feature):
        m = hashlib.md5()
        m.update(feature.encode())
        res = m.hexdigest()
        return res.upper() + "|0"

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

    ns = LocateDownloadSign(uid, bduss)
    timestamp = ns.time
    devuid = ns.dev_uid
    rand = ns.rand
    
    # Use the fs_id to locate the download URL
    locate_params = {
        "apn_id": "1_0",
        "app_id": "250528",
        "channel": "0",
        "check_blue": "1",
        "clienttype": "17",
        "es": "1",
        "esl": "1",
        "freeisp": "0",
        "method": "locatedownload",
        "path": path,
        "queryfree": "0",
        "use": "0",
        "ver": "4.0",
        "time": timestamp,
        "rand": rand,
        "devuid": devuid,
        "cuid": devuid
    }

    base_url = "https://pcs.baidu.com/rest/2.0/pcs/file"
    query_string = urllib.parse.urlencode(locate_params, safe='|')
    
    retry_attempts = 3
    for attempt in range(retry_attempts):
        response = requests.get(base_url + "?" + query_string, headers=headers, cookies=cookies)
        if response.status_code == 200:
            try:
                url_info = response.json()
                if "urls" not in url_info:
                    if url_info.get('errno') == 9019:
                        print("Verification required. Please complete any necessary verification steps on the Baidu website.")
                        break
                    raise Exception("'urls' key not found in the response.")
                return [url["url"] for url in url_info["urls"]]
            except json.JSONDecodeError as e:
                raise Exception("Failed to decode JSON response: {}".format(e))
        elif response.status_code == 500:
            print(f"Internal server error on attempt {attempt + 1}, retrying...")
            time.sleep(1)
        else:
            raise Exception("Failed to locate file: status code {}".format(response.status_code))
    
    raise Exception("Failed to locate file after multiple attempts.")

def download_with_aria2c(urls, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Use the last URL for downloading
    url = urls[-1]

    # Check if the file already exists
    '''
    file_name = os.path.basename(urllib.parse.urlparse(url).path)
    file_path = os.path.join(output_dir, file_name)
    if os.path.exists(file_path):
        print(f"{file_path} already exists, skipping download.")
        return
    '''
    command = ["aria2c", "-d", output_dir, "--user-agent", "netdisk", url]
    #print(" ".join(command))
    subprocess.run(command)

def main():
    parser = argparse.ArgumentParser(description="BaiduPCS-Go in Python")
    parser.add_argument("command", choices=["login", "who", "ls", "locate"], help="Command to execute")
    parser.add_argument("--bduss", help="BDUSS for login")
    parser.add_argument("--path", help="Path for ls or locate command")
    parser.add_argument("--from-pan", action="store_true", help="Locate from pan")
    parser.add_argument("--output-dir", help="Output directory for download", default="./downloads")

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
            print(f"User Info: UID={user_info.base.uid}, Name={user_info.base.name}")
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
            print(f"User Info: UID={user_info.base.uid}, Name={user_info.base.name}")
            uid = user_info.base.uid
            urls = locate_file(bduss, args.path, uid)
            for url in urls:
                #print(url)
                pass
            print("正在下载：", args.path)
            download_with_aria2c(urls, args.output_dir)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
