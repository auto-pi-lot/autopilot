import requests
import sys
import re
import json
import os
from tqdm import tqdm

def download_box(file_url, filename = None, save_path = None):
    """
    Download a file from Box from a URL.

    eg. https://flir.app.boxcn.net/v/SpinnakerSDK/file/545648953427

    Note::

        Only works for files that don't require authentication

    Args:
        file_url (str): A URL of a preview page on Box
        filename (str): Filename (without path) to save file. If None, the filename from the server is used
        save_path (str): A path to save the file to. If None, current directory is used

    Returns:
        filename (str): the complete path that the file has been saved to

    """
    sess = requests.Session()


    if isinstance(file_url, bytes):
        file_url = file_url.decode('utf-8')

    if isinstance(filename, bytes):
        filename = filename.decode('utf-8')

    if isinstance(save_path, bytes):
        save_path = save_path.decode('utf-8')


    file_name = "file_"+file_url.split('/')[-1]
    file_number = file_url.split('/')[-1]
    base_url = '/'.join(file_url.split('/')[0:3])
    share_url = '/'.join(file_url.split('/')[0:5])

    page = sess.get(file_url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:70.0) Gecko/20100101 Firefox/70.0"
        },
        cookies={},
    )



    req_parts = {
        'z': page.cookies.get('z'),
        'box_visitor_id': page.cookies.get('box_visitor_id'),
        'bv': page.cookies.get('bv'),
        'cn': page.cookies.get('cn'),
        'token': re.search('(?<=\"requestToken\":\")(.+?)(?=\")', page.content.decode('utf-8')).group(0)
    }


    tokens = sess.post("https://flir.app.boxcn.net/app-api/enduserapp/elements/tokens",
        json={'fileIDs':[file_name]},
        headers={
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "DNT": "1",
            "Origin": base_url,
            "Referer": file_url,
            "Request-Token": "{}".format(req_parts['token']),
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:70.0) Gecko/20100101 Firefox/70.0",
            "X-Box-Client-Name": "enduserapp",
            "X-Box-Client-Version": "20.162.1",
            "X-Box-EndUser-API": "vanityName=SpinnakerSDK",
            "X-Request-Token": "{}".format(req_parts['token'])
        },
    )

    req_parts['dl_token'] = json.loads(tokens.content)[file_name]['read']

    dl_link = sess.get("https://api.box.com/2.0/files/{}?fields=download_url".format(file_number),
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "Authorization": "Bearer {}".format(req_parts['dl_token']),
            "BoxApi": "shared_link={}".format(share_url),
            "Connection": "keep-alive",
            "DNT": "1",
            "Origin": base_url,
            "Referer": file_url,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:70.0) Gecko/20100101 Firefox/70.0",
            "X-Box-Client-Name": "box-content-preview",
            "X-Box-Client-Version": "2.23.0",
            "X-Rep-Hints": "[3d][pdf][text][mp3][jpg?dimensions=1024x1024&paged=false][jpg?dimensions=2048x2048,png?dimensions=2048x2048][dash,mp4][filmstrip]"
        },
    )

    dl_url = json.loads(dl_link.content)['download_url']

    dl_file = sess.get(dl_url, stream=True)

    if filename is None:
        filename = re.search("filename=\"(.+?)\";", dl_file.headers.get('Content-Disposition')).groups(0)[0]
    if save_path:
        filename = os.path.join(save_path, filename)

    total_size = int(dl_file.headers.get('content-length', 0))
    block_size = 1024  # 1 Kibibyte
    t = tqdm(total=total_size, unit='iB', unit_scale=True)
    with open(filename, 'wb') as output_file:
        for data in dl_file.iter_content(block_size):
            t.update(len(data))
            output_file.write(data)
    t.close()

    sys.stdout.write(filename)
