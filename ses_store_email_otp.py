from bs4 import BeautifulSoup
from email import message_from_bytes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import boto3
import time


def create_multipart_message(
        sender: str, recipients: list, title: str, text: str=None, html: str=None, attachments: list=None)\
        -> MIMEMultipart:
    """
    From https://stackoverflow.com/a/52105406/10231083

    Creates a MIME multipart message object.
    Uses only the Python `email` standard library.
    Emails, both sender and recipients, can be just the email string or have the format 'The Name <the_email@host.com>'.

    :param sender: The sender.
    :param recipients: List of recipients. Needs to be a list, even if only one recipient.
    :param title: The title of the email.
    :param text: The text version of the email body (optional).
    :param html: The html version of the email body (optional).
    :param attachments: List of files to attach in the email.
    :return: A `MIMEMultipart` to be used to send the email.
    """
    multipart_content_subtype = 'alternative' if text and html else 'mixed'
    msg = MIMEMultipart(multipart_content_subtype)
    msg['Subject'] = title
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)

    # Record the MIME types of both parts - text/plain and text/html.
    # According to RFC 2046, the last part of a multipart message, in this case the HTML message, is best and preferred.
    if text:
        part = MIMEText(text, 'plain')
        msg.attach(part)
    if html:
        part = MIMEText(html, 'html')
        msg.attach(part)

    # Add attachments
    for attachment in attachments or []:
        with open(attachment, 'rb') as f:
            part = MIMEApplication(f.read())
            part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(attachment))
            msg.attach(part)

    return msg

def send_mail(
        sender: str, recipients: list, title: str, text: str = None, html: str = None, attachments: list = None) -> dict:
    """
    From https://stackoverflow.com/a/52105406/10231083
    
    Send email to recipients. Sends one mail to all recipients.
    The sender needs to be a verified email in SES.
    """
    msg = create_multipart_message(
        sender, recipients, title, text, html, attachments)
    ses_client = boto3.client('ses')  # Use your settings here
    return ses_client.send_raw_email(
        Source=sender,
        Destinations=recipients,
        RawMessage={'Data': msg.as_string()}
    )


def lambda_handler(event, context, debug=None):

    print('Parsing Email at time:\n{0}'.format(time.time()))

    if not debug:
        record = event['Records'][0]
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
    else:
        # debug is in the form of (bucket, key)
        bucket = debug[0]
        key = debug[1]
    s3_client = boto3.client('s3')
    response = s3_client.get_object(Bucket=bucket, Key=key)
    msg = message_from_bytes(response['Body'].read())
    recipient = [s.replace('<', '').replace('>', '')
                 for s in msg['to'].split(' ') if '@' in s][0]
    sender_unformatted = msg['from']
    sender = [s.replace('<', '').replace('>', '')
              for s in msg['from'].split(' ') if '@' in s][0]
    subject = msg['subject']
    body = ''
    if msg.is_multipart():
        print('Message is MultiPart')
        for payload in msg.get_payload():
            if payload and payload.get_payload(decode=True).decode('utf8'):
                body += payload.get_payload(decode=True).decode('utf8')
                break # only add the html part if text + html, which should be first
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body += payload.decode()
    if body:
        email_soup = BeautifulSoup(body, 'lxml')
    else:
        return 1
    print('From:', sender_unformatted)
    print('Subject:', subject)
    print('To:', recipient)
    from_key = '{}/{}'.format(bucket, key)
    # check if this is a giveaway win notification
    if sender == 'giveaway-notification@amazon.com':
        from_email = '<SES VERIFIED FROM EMAIL>'
        forward_emails = ['<SES VERIFIED TO EMAIL>']
        email_client = boto3.client('ses')
        send_response = send_mail(sender=from_email, recipients=forward_emails, title=subject, html=body, attachments=None)
        to_key = 'wins/{email}/{time:.2f}'.format(email=recipient, time=time.time())
        s3_client.copy_object(Bucket=bucket, CopySource=from_key, Key=to_key)
        s3_client.delete_object(Bucket=bucket, Key=key)
        print('Moved email from {} to {}'.format(from_key, to_key))
        if 'MessageId' in send_response:
            if len(forward_emails) == 1:
                forward_emails = forward_emails[0]
            print('Sent email from {from_email} to {to_email}. Message ID: {id}'.format(
                from_email=from_email, to_email=forward_emails, id=send_response['MessageId']))
            return 0
        else:
            print('Error sending email')
            return 1
    otp = None
    try:
        otp = email_soup.find_all('p', class_="otp")
        assert len(otp) == 1  # should only be one of these items (as of now)
        otp = otp[0].get_text()
        print('Found OTP:', otp)
    except:
        print('Could not find OTP')
    if otp:
        to_key = 'sorted/{email}/{time:.2f}-{OTP}'.format(email=recipient, time=time.time())
        s3_client.copy_object(Bucket=bucket, CopySource=from_key, Key=to_key, OTP=otp)
    else:
        to_key = 'sorted/{email}/{time:.2f}'.format(email=recipient, time=time.time())
        s3_client.copy_object(Bucket=bucket, CopySource=from_key, Key=to_key)
    s3_client.delete_object(Bucket=bucket, Key=key)
    print('Moved email from {} to {}'.format(from_key, to_key))
    return 0


if __name__ == '__main__':
    test_bucket = '<TEST BUCKET>'
    test_key = '<TEST KEY>'
    lambda_handler(0, 0, (test_bucket, test_key))
