from pathlib import Path
import tempfile
import urllib.request
import fitz

pdf_path = Path(tempfile.gettempdir()) / 'resume-upload-test.pdf'
doc = fitz.open()
p = doc.new_page()
p.insert_text((72, 72), 'Jane Doe\nSoftware Engineer\nPython, FastAPI, React\nSeattle, WA\n jane@example.com')
doc.save(pdf_path)
doc.close()

boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
body = []
body.append(f'--{boundary}\r\n'.encode())
body.append(b'Content-Disposition: form-data; name="file"; filename="resume-upload-test.pdf"\r\n')
body.append(b'Content-Type: application/pdf\r\n\r\n')
body.append(pdf_path.read_bytes())
body.append(f'\r\n--{boundary}--\r\n'.encode())
req = urllib.request.Request('http://127.0.0.1:8010/api/resume/upload', data=b''.join(body), method='POST')
req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
with urllib.request.urlopen(req, timeout=30) as resp:
    print(resp.read().decode())
