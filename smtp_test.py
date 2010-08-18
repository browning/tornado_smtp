import smtpserver
import tornado.ioloop

def handle_msg(msg):
    print "subject: " + msg['subject']

smtp_server = smtpserver.SMTPServer(handle_msg)
smtp_server.listen(25)
tornado.ioloop.IOLoop.instance().start()

