import smtpserver
import tornado.ioloop


smtp_server = smtpserver.SMTPServer("none")
smtp_server.listen(1337)
tornado.ioloop.IOLoop.instance().start()

