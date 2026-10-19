"""The text of the privacy and terms pages (PHP: the $P array in index.php).
Each section is (heading, text, extra): extra is False, True (add the contact line) or "mail" (add the recovery-email sentence)."""

MAIL_ON = (" An email address is optional: if you add one for password recovery, we keep it encrypted, use it only to send you "
           "confirmation, reset and security messages, and pass it to our email provider (Brevo) to deliver them. You can remove it any time in Settings.")
MAIL_OFF = " We do not ask for an email address."

PAGES = {'privacy': ('Privacy',
             'Last updated October 2026. Masque is built to need as little about you as possible.',
             [('What we keep',
               'Your username, a hashed password (nobody can read it, including us), the optional name, bio and pictures you add, and everything you '
               'post or send: posts, comments, photos, chat messages, friends, likes, reactions, votes and questions. We do not ask for a phone number or real name.',
               'mail'),
              ('Your Masque',
               'Other people are not shown which account a Masque belongs to. If a Masque or its content is reported, an admin '
               'can see the account behind it so they can deal with abuse. Revealing your Masque is always your choice.',
               False),
              ('Anonymous questions',
               'They are anonymous to the person you ask. Masque still records who sent a question, so abuse can be handled if '
               'it is reported.',
               False),
              ('Devices and IP addresses',
               'The active devices list stores a browser and system label (like "Chrome on Android") and when each device was '
               'last used. It does not store IP addresses. Your IP address is used briefly to limit sign-in and sign-up attempts '
               'and to slow down spam, and those records are cleared automatically.',
               False),
              ('Photos', 'Photo metadata (such as GPS location) is removed when you upload.', False),
              ('Cookies and tracking',
               'Masque uses one cookie to keep you signed in. There are no ads, no analytics and no trackers. Fonts are loaded '
               'from Google Fonts, so Google can see that your browser requested them.',
               False),
              ('Messages',
               'Chats are private to the people in them but are not end-to-end encrypted. Admins with access to the server could '
               'technically read the stored data, and we only do that to investigate abuse or fix problems.',
               False),
              ('Who sees what',
               'Posts are shown according to the privacy you choose: Everyone, Friends or Only me. Private accounts only show '
               'posts to friends. Blocked people cannot see or contact you.',
               False),
              ('Deleting your data',
               'Settings has a Delete account button that removes your profile, posts, photos, comments, chats and friends. '
               'Posts that you set to disappear are deleted automatically when time runs out. Backups made for safety are kept '
               'for a few days and then deleted, so deleted data can remain in an old backup for a short time.',
               False),
              ('Your recovery code',
               'There is no email on Masque, so a lost password can only be reset with your recovery code. Keep it private: '
               'anyone who has it and your username can take over your account.',
               False),
              ('Changes and contact', 'If this page changes in an important way, we will say so inside Masque. ', True)]),
 'terms': ('Terms',
           'Last updated October 2026. By making an account you agree to these rules.',
           [('Playing with identity is fine',
             'Masque is a place to be anyone you like. Characters, personas and made-up names are welcome. Pretending to be a '
             'real person in order to deceive, harass or harm them is not.',
             False),
            ('Be kind and be safe',
             "No harassment, threats, hate, or sexual content involving minors. Do not post other people's private information, "
             'or anything illegal. Photos that are sensitive should be blurred with the sensitive-content option.',
             False),
            ('No spam or abuse of the site',
             'No spam, scams, fake accounts made to dodge a ban, or attempts to break or overload Masque. New accounts have some '
             'tighter limits for the first day.',
             False),
            ('Your content',
             'You keep ownership of what you post. By posting, you let Masque store and show it to the people you chose, so the '
             'app can work. Only post things you have the right to share.',
             False),
            ('Moderation',
             'Anyone can report content. Admins can hide, blur or remove content, hold posts that match the word filter, and '
             'suspend or ban accounts. A suspended or banned account can read but not post or send, and can send one appeal from '
             'the banner.',
             False),
            ('Your account',
             'Keep your password and recovery code safe. You are responsible for what happens on your account. You can delete it '
             'at any time in Settings.',
             False),
            ('No guarantees',
             'Masque is provided as it is. It may go down for maintenance, and features can change. We try to keep backups, but '
             'cannot promise that nothing will ever be lost, so keep your own copy of anything important.',
             False),
            ('Contact', 'Questions or problems with these terms: ', True)])}
