
from getmailcore.message import Message
from getmailcore.exceptions import *

import os, smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import EmailMessage

greetru = "привет"
greetde = "Grüße"
byeru = 'пока'

def test_add_header():
    m = EmailMessage()
    m["Subject"] = "test"
    m["From"] = "my@gmail.com"
    m["To"] = "your@gmail.com"
    t = greetru.encode('Windows-1251')
    m.set_content(t,'text','plain')
    #m.as_string()
    #m.get_content()
    #m.get_content_charset()
    #m.get_charsets()
    gm = Message(fromstring=m.as_bytes())
    #te.decode('Windows-1251')
    gm.add_header('X-byeru',byeru)
    assert gm.content()['X-byeru'] == byeru
    ge = greetde.encode('latin1')
    gm.add_header('X-greetde',ge)
    #gm.content()['X-greetde']
    assert gm.content()['X-greetde'] != greetde

def test_add_header1():
    m = EmailMessage()
    m["Subject"] = "test"
    m["From"] = "my@gmail.com"
    m["To"] = "your@gmail.com"
    t = greetru.encode('Windows-1251')
    m.set_content(t,'text','plain')
    m.set_param('charset','Windows-1251')
    #m.as_string()
    #m.get_content()
    #m.get_content_charset()
    #m.get_charsets()
    gm = Message(fromstring=m.as_bytes())
    te = byeru.encode('Windows-1251')
    #te.decode('Windows-1251')
    gm.add_header('X-byeru',te)
    assert gm.content()['X-byeru'] == byeru
    ge = greetde.encode('latin1')
    gm.add_header('X-greetde',ge)
    #gm.content()['X-greetde']
    ### if coding is really wrong: no way
    assert gm.content()['X-greetde'] != greetde

def test_add_header2():
    mm = MIMEMultipart("alternative")
    mm["Subject"] = "multipart test"
    mm["From"] = "my@gmail.com"
    mm["To"] = "your@gmail.com"
    p1 = MIMEText(greetru, "plain")
    p1.set_param('charset','Windows-1251')
    p2 = MIMEText(greetde, "plain")
    p2.set_param('charset','latin1')
    mm.attach(p1)
    mm.attach(p2)
    #mm.get_charsets()
    gmm = Message(fromstring=mm.as_bytes())
    te = byeru.encode('Windows-1251')
    #te.decode('Windows-1251')
    gmm.add_header('X-byeru',te)
    assert gmm.content()['X-byeru'] == byeru
    ge = greetde.encode('latin1')
    gmm.add_header('X-greetde',ge)
    #gmm.content()['X-greetde']
    ### if coding is really wrong: no way
    assert gmm.content()['X-greetde'] != greetde
    #mm.as_string()

def test_spam_1():
    fl = os.path.join(os.path.split(__file__)[0],'spam.eml')
    with open(fl,'br') as f:
        spam_eml = f.read()
    gm = Message(fromstring=spam_eml)
    gmfl = gm.flatten(None,None)
    assert b'corrupt' in gmfl # check recover

def test_spam_2():
    fl = os.path.join(os.path.split(__file__)[0],'spam.eml')
    gmm = Message(fromfile=open(fl,'rb'))
    try:
        gmfl = gmm.flatten(None,None)
    except getmailDeliveryError as o:
        assert 'could not recover' in str(o)
