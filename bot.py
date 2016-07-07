import logging
import time
import sys
import os
from contextlib import contextmanager

from EmojiHandler import EmojiHandler
from GoogleApi import Translator
from slack import UniChatSlackClient
from itchat.client import client as WeChatClient


@contextmanager
def tmp_file():
    tmp_filename = os.tmpnam()
    yield tmp_filename
    os.unlink(tmp_filename)


class Bot(object):
    def __init__(self, token, channelName, googleApikey):
        self.channelName = channelName
        self.slackClient = UniChatSlackClient(token)
        self.wechatGroup = None
        self.wechatClient = WeChatClient()
        self.translator = Translator(googleApikey)
        self.emojiHandler = EmojiHandler()
        self.media_types = set(['Picture', 'Recording', 'Video'])

    def bot_main(self):
        self.channel = self.slackClient.attach_channel(self.channelName)
        self.wechatClient.auto_login()

        while True:
            group_messages = self.receive_wechat_group_msgs()
            self.process_wechat_messages(group_messages)
            slack_messages = self.slackClient.read_messages_in_channels()
            self.process_slack_messages(slack_messages)
            time.sleep(.5)

    def receive_wechat_group_msgs(self):
        client = self.wechatClient
        if not client.storageClass.msgList:
            return []
        msgs = []
        while client.storageClass.msgList:
            msg = client.storageClass.msgList.pop()
            if '@@' in msg.get('FromUserName'):
                msgs.append(msg)
        return msgs

    def forward_wechat_file(self, msg):
        with tmp_file() as file_name:
            download_func = msg['Text']
            print "Saving WeChat file to " + file_name
            download_func(file_name)
            #os.fsync() # Make sure the image is written to disk
            title = msg['ActualNickName'] + " shared an image"
            print "Uploading image to slack: %s" % file_name
            self.slackClient.send_file_to_channel(self.channel.id, file_name, title)

    def forward_slack_image(self, user_name, msg):
        with tmp_file() as file_name:
            print "Saving Slack image to " + file_name
            if self.slackClient.extract_file(msg, file_name):
                print "Uploading image to WeChat: %s" % file_name
                self.wechatClient.send_msg("%s shared a file: %s" % (user_name, msg[u'file'][u'name']), self.wechatGroup)
                self.wechatClient.send_image(file_name, self.wechatGroup)

    def process_wechat_messages(self, msgs):
        for msg in msgs:
            print("WeChat group: %s" % msg['FromUserName'])
            if not self.wechatGroup:
                self.wechatGroup = msg['FromUserName']

            print("Got WeChat message: %s" % msg)
            print("Sending message to slack: %s" % msg['Text'])
            if msg['Type'] in self.media_types:
                self.forward_wechat_file(msg)
            else:
                # TODO Doesn't look so nice to use `channel` directly.
                updatedMsg = self.emojiHandler.weChat2Slack(msg['Content'], self.translator.toEnglish)
                self.channel.send_message(msg['ActualNickName'] + ": " + msg['Text'])
                self.channel.send_message("[Translation]: %s: %s" % (msg['ActualNickName'], updatedMsg))

    def process_slack_messages(self, msgs):
        for msg in msgs:
            if self.wechatGroup:
                print("Got slack message: %s" % msg)
                print("Sending message to wechat: %s" % msg[u'text'])
                user_name = self.slackClient.get_user_name(msg[u'user'])

                if u'subtype' in msg and msg[u'subtype'] == u'file_share':
                    self.forward_slack_image(user_name, msg)
                else:
                    translatedMsg = self.translator.toChinese(msg[u'text'])
                    updatedMsg = self.emojiHandler.slack2WeChat(msg[u'text'], self.translator.toChinese)
                    self.wechatClient.send_msg("%s: %s" % (user_name, msg[u'text']), self.wechatGroup)
                    self.wechatClient.send_msg("[Translation]: %s : %s" % (user_name, updatedMsg), self.wechatGroup)
            else:
                print("No WeChat group")


def main():
    token = sys.argv[1]
    channel = sys.argv[2]
    googleApikey = sys.argv[3]
    bot = Bot(token, channel, googleApikey)
    print("Starting bot...")
    bot.bot_main()


if __name__ == "__main__":
    main()
