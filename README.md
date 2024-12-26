# Claude Telegram Bot

## Introduction

This is a Telegram Chatbot that integrates with the [Claude API from Anthorpic](https://claude.ai/).

The code is somewhat still in a MVP/alpha state, the basic functionalities are there but I would need a more polished deployment pipeline as well as some cleanup and refactoring of the code. The bot was originally written for my own use and therefore not everything is very "polished" yet.


## Why?

1. **Opus model support**: Anthropic has taken down the support for Opus model from their free plan and made it available to only paid users. (You can see a comparison list of various Claude models [here](https://docs.anthropic.com/en/docs/about-claude/models#model-comparison-table)). However Opus remains available from the API.
2. **Cost**: The Pro version of Anthropic cost 20USD per month, the API cost is much lower (the price of their most expensive Opus model API is 15USD/million token input and 35USD/million token output, with 3.5 Haiku to cost 0.80USD and 4USD for milion token input and output respectively).
3. **Free plan limitations**: Free plan would switch to concise mode when the server is busy, there is also conversation length restrictions, etc. While this solution is not completely free, one can expect single digit per month cost for light usage.
4. Just something fun to do!

## Prerequsite

You will need to set up an Anthropic API key before using the program, Anthropic has a quite [comprehensive documentation](https://docs.anthropic.com/en/docs/initial-setup) on this so I won't try to repeat it here. Note that you will need to have a credit card and put in some minimal credit (10USD would last you a while if you are not a heavy user) before being able to use the API.

You will also need to set up a Telegram bot, that's again a very simple process (in fact one of the things I like about Telegram is how easy it is to set it up):

1. You will need to download and install Telegram app from the app store and follow the steps to create a Telegram account with your phone number (if you don't have one).
2. Search and add [BotFather](https://telegram.me/BotFather) as your newest friend.
3. Start a chat with BotFather, and start creating a new bot using the command <code>/newbot</code>.
4. Go through the conversation and get a name and an username for your bot, note the username has to end with 'bot' (Case insensitive).
5. Once it is done, take note of the token (On Android you can just press and hold anywhere on the token string to copy it), note that there are two parts of the token and you will need to copy everything together including the colon (:).

If you would like to restrict the bot to only be usable by the Telegram users you trust, you will also need to get user IDs of those user accounts. The user ID is a nine digit numerical ID and is different from your username. To find your userID you can start a conversation with [IDBot](https://telegram.me/myidbot) and use <code>/getid</code> command to get your ID.

**Note:** When I was searching for these bots recently I do see there are quite a lot of similarly named bots showing up in the results. I would suggest to proceed with caution when it comes to those bots, especially if there are very few active users (you can see the active monthly users in the search results, and BotFather and IDBot should both have at least tens of thousands of active monthly users).

Finally, you will also need to have a [Heroku](https://www.heroku.com/home) account if you would like to deploy to Heroku, note that if you are a student, Heroku is part of the [GitHub Student Developer Pack](https://education.github.com/pack) offering which would give you a credit of 13USD per month for 24 months, more details can be found [here](https://www.heroku.com/github-students).

## Deployment

Currently only deployment to Heroku is available, I will add a docker deployment soon.

For Heroku deployment:

1. Install Heroku CLI

   Since this part is OS dependent, please follow the instructions [here](https://devcenter.heroku.com/articles/heroku-cli)
   
2. Login to Heroku
   
        heroku login
   
3. Create Heroku app
   
        heroku create YOUR_APP_NAME

   Replace "YOUR_APP_NAME" with the name of the app desired, I used <code>claude-telegram-bot</code> since I am a very uncreative guy, but feel free to pick any name as long as it is unique wihtin your account. 
   
4. Set configuration variables
   
        heroku config:set \
                TELEGRAM_BOT_TOKEN=your_telegram_bot_token \
                ANTHROPIC_API_KEY=your_claude_api_key \
                ALLOWED_USERS=user1_id,user2_id
  
5. Deploy to Heroku
   
        git add .
        git commit -m "Heroku deployment"
        git push heroku main
   
6. Ensure one worker dyno
   
        heroku ps:scale worker=1

## TroubleShooting

If using Heroku you can see the app logs via the cli:

    heroku logs --app --YOUR_APP_NAME

Replace YOUR_APP_NAME with the name of the app you've specified in the deployment section. You can also limit the number of the lines of the log by specifying the <code>-n</code> option.

## Credits

- [ChatGPT Telegram Bot](https://github.com/father-bot/chatgpt_telegram_bot) for giving me the inspiration to develop something similar and for giving me some tips and tricks when interacting with the Telegram bot API.
- [Claude](https://claude.ai) for guiding me through the development, in particular, the deployment steps.