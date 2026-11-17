"""Docker-only integration check. Creates and cleans up its own container/volume.

Requires a previously built image and a Docker engine. Uses a real public leaf
photograph and real inference; does not target or modify a running user service.
"""
import argparse
import http.cookiejar
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()


def wait_ready(url):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + '/healthz', timeout=4) as response:
                if response.status == 200 and json.load(response)['status'] == 'ready':
                    return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise RuntimeError('Container did not become ready within 180 seconds')


def main(image):
    name = 'crop-smoke-' + uuid.uuid4().hex[:12]
    volume = name + '-data'
    created = False
    docker('volume', 'create', volume)
    try:
        docker('run', '-d', '--name', name, '--memory=2g',
               '-p', '127.0.0.1::10077', '--mount', f'source={volume},target=/var/data',
               '-e', 'PORT=10077', '-e', 'FORCE_HTTPS=false',
               '-e', 'SESSION_SECURE_COOKIE=false', '-e', 'APP_URL=http://localhost:10077', image)
        created = True
        details = json.loads(docker('inspect', name))[0]
        port = details['NetworkSettings']['Ports']['10077/tcp'][0]['HostPort']
        url = 'http://127.0.0.1:' + port
        wait_ready(url)
        print('PASS: custom public PORT, Laravel, SQLite and offline model readiness', flush=True)

        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with client.open(url + '/', timeout=15) as response:
            html = response.read().decode()
        token = re.search(r'name="_token" value="([^"]+)"', html).group(1)
        # Public real PlantVillage photo, pinned to an immutable dataset commit.
        photo_url = ('https://raw.githubusercontent.com/spMohanty/PlantVillage-Dataset/'
                     '7f7ecc7e1eaca78107e3affe7cb5abd9427e139a/raw/color/Tomato___Early_blight/'
                     '0012b9d2-2130-4a06-a834-b1f3af34f57e___RS_Erly.B%208389.JPG')
        with urllib.request.urlopen(photo_url, timeout=30) as response:
            photo = response.read(5 * 1024 * 1024 + 1)
        assert 0 < len(photo) <= 5 * 1024 * 1024
        boundary = 'crop-smoke-' + uuid.uuid4().hex
        body = b''
        for key, value in [('_token', token), ('crop', 'tomato')]:
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="leaf.jpg"\r\n'
                 'Content-Type: image/jpeg\r\n\r\n').encode() + photo + f'\r\n--{boundary}--\r\n'.encode()
        request = urllib.request.Request(url + '/detect', data=body,
                                         headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        with client.open(request, timeout=150) as response:
            html = response.read().decode()
        assert 'Analysis complete' in html and 'MobileNetV2 v1.1' in html, 'Real prediction was not rendered'
        print('PASS: CSRF/session multipart upload through Nginx and Laravel to actual model', flush=True)

        # Save a test-only marker and key fingerprint, never the key itself.
        probe = ("import sqlite3,hashlib,json; from pathlib import Path; "
                 "c=sqlite3.connect('/var/data/database.sqlite'); "
                 "c.execute('CREATE TABLE IF NOT EXISTS deployment_probe (value INTEGER)'); "
                 "c.execute('INSERT INTO deployment_probe VALUES (17)'); c.commit(); "
                 "print(json.dumps({'key_sha256':hashlib.sha256(Path('/var/data/app.key').read_bytes()).hexdigest(),"
                 "'value':c.execute('SELECT value FROM deployment_probe').fetchone()[0]}))")
        before = json.loads(docker('exec', name, 'python', '-c', probe))
        docker('restart', name)
        wait_ready(url)
        verify = ("import sqlite3,hashlib,json; from pathlib import Path; "
                  "c=sqlite3.connect('/var/data/database.sqlite'); "
                  "print(json.dumps({'key_sha256':hashlib.sha256(Path('/var/data/app.key').read_bytes()).hexdigest(),"
                  "'value':c.execute('SELECT value FROM deployment_probe').fetchone()[0]}))")
        after = json.loads(docker('exec', name, 'python', '-c', verify))
        assert before == after and after['value'] == 17
        print('PASS: SQLite contents and generated APP_KEY survive container restart', flush=True)
    except Exception:
        if created:
            print(docker('logs', '--tail', '120', name), flush=True)
        raise
    finally:
        if created:
            subprocess.run(['docker', 'rm', '-f', name], check=False)
        subprocess.run(['docker', 'volume', 'rm', volume], check=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='crop-disease-render')
    main(parser.parse_args().image)
