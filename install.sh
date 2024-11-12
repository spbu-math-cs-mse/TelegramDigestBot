git clone https://github.com/haboh/TelegramDigestBotSecrets.git
cp -f TelegramDigestBotSecrets/credentials.txt recommendation-system/assets
cp -f TelegramDigestBotSecrets/token.txt recommendation-system/assets
cp -f TelegramDigestBotSecrets/credentials.txt telegram-bot/assets
cp -f TelegramDigestBotSecrets/token.txt telegram-bot/assets
rm -rf TelegramDigestBotSecrets
