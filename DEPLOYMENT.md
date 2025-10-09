# Deployment Guide

This guide covers deploying the Claude Telegram Bot to GitHub and then to Heroku using containers.

## Prerequisites

1. **GitHub Account**: For repository hosting
2. **Heroku Account**: For application deployment
3. **Heroku CLI**: Install from https://devcenter.heroku.com/articles/heroku-cli
4. **Git**: For version control

## Step 1: Prepare for GitHub Deployment

### 1.1 Initialize Git Repository (if not already done)
```bash
git init
git add .
git commit -m "Initial commit: Claude Telegram Bot"
```

### 1.2 Create GitHub Repository
1. Go to GitHub and create a new repository
2. **DO NOT** initialize with README, .gitignore, or license (we already have these)
3. Copy the repository URL

### 1.3 Push to GitHub
```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

## Step 2: Set Up Heroku Deployment

### 2.1 Install Heroku CLI
```bash
# On Windows (using Chocolatey)
choco install heroku-cli

# On macOS (using Homebrew)
brew install heroku/brew/heroku

# On Ubuntu/Debian
sudo snap install --classic heroku
```

### 2.2 Login to Heroku
```bash
heroku login
```

### 2.3 Create Heroku Application
```bash
# Create app with a specific name
heroku create your-bot-name

# Or let Heroku generate a random name
heroku create
```

### 2.4 Set Stack to Container
```bash
heroku stack:set container -a your-app-name
```

## Step 3: Configure Environment Variables

Set up your environment variables in Heroku (replace with your actual values):

### 3.1 Required Variables
```bash
heroku config:set TELEGRAM_BOT_TOKEN="your_telegram_bot_token" -a your-app-name
heroku config:set ANTHROPIC_API_KEY="your_anthropic_api_key" -a your-app-name
```

### 3.2 Optional Configuration Variables
```bash
# User access control (comma-separated user IDs)
heroku config:set ALLOWED_USERS="123456789,987654321" -a your-app-name

# Bot configuration
heroku config:set DEFAULT_CLAUDE_MODEL="claude-3-5-sonnet-latest" -a your-app-name
heroku config:set MAX_HISTORY_LENGTH="10" -a your-app-name
heroku config:set MODEL_CACHE_DURATION_HOURS="1" -a your-app-name

# Logging configuration
heroku config:set LOG_LEVEL="INFO" -a your-app-name
heroku config:set ENABLE_FILE_LOGGING="true" -a your-app-name
heroku config:set LOG_DIRECTORY="./logs" -a your-app-name

# Database (Heroku will use ephemeral storage)
heroku config:set DATABASE_PATH="bot_data.db" -a your-app-name
```

### 3.3 View Current Config
```bash
heroku config -a your-app-name
```

## Step 4: Deploy to Heroku

### 4.1 Connect Heroku to GitHub Repository
```bash
# Add Heroku remote (if created via CLI)
heroku git:remote -a your-app-name

# Or connect via Heroku Dashboard
# Go to your app -> Deploy tab -> GitHub -> Connect repository
```

### 4.2 Deploy Using Git
```bash
git push heroku main
```

### 4.3 Scale the Worker Process
```bash
heroku ps:scale worker=1 -a your-app-name
```

## Step 5: Monitor and Manage

### 5.1 View Logs
```bash
# Real-time logs
heroku logs --tail -a your-app-name

# Recent logs
heroku logs -a your-app-name
```

### 5.2 Check Application Status
```bash
heroku ps -a your-app-name
```

### 5.3 Restart Application
```bash
heroku restart -a your-app-name
```

## Step 6: Automatic Deployments (Optional)

### 6.1 Enable Auto-Deploy from GitHub
1. Go to Heroku Dashboard → Your App → Deploy tab
2. Connect to GitHub repository
3. Enable "Automatic deploys" from main branch
4. Enable "Wait for CI to pass before deploy" (recommended)

### 6.2 Manual Deploy from GitHub
1. Go to Deploy tab in Heroku Dashboard
2. Scroll to "Manual deploy" section
3. Select branch and click "Deploy Branch"

## Important Notes

### Database Considerations
- **Heroku uses ephemeral storage** - database will reset on app restart
- For production, consider using **Heroku Postgres** addon:
  ```bash
  heroku addons:create heroku-postgresql:hobby-dev -a your-app-name
  ```
- Update `DATABASE_PATH` to use `DATABASE_URL` environment variable for Postgres

### Security Best Practices
1. **Never commit sensitive data** (API keys, tokens)
2. **Use environment variables** for all configuration
3. **Regularly rotate API keys**
4. **Monitor application logs** for suspicious activity
5. **Set up ALLOWED_USERS** to restrict bot access

### Cost Management
- **Free tier limitations**: 550-1000 free dyno hours per month
- **Worker dynos**: Don't sleep like web dynos (good for bots)
- **Monitor usage** in Heroku Dashboard

### Troubleshooting

#### Common Issues:

1. **Build Failure**: Check Dockerfile and requirements.txt
2. **Environment Variables**: Ensure all required vars are set
3. **Port Issues**: Bot doesn't need to bind to PORT (not a web server)
4. **Memory Issues**: Monitor memory usage, upgrade dyno if needed

#### Debug Commands:
```bash
# Check build logs
heroku logs --source build -a your-app-name

# Check worker logs
heroku logs --dyno worker -a your-app-name

# Access container shell
heroku run bash -a your-app-name
```

## File Structure Summary

```
claude-telegram-bot-multiple/
├── .gitignore              # Excludes sensitive files from Git
├── .dockerignore          # Excludes files from Docker build
├── Dockerfile             # Container configuration
├── heroku.yml             # Heroku container deployment config
├── requirements.txt       # Python dependencies
├── DEPLOYMENT.md          # This deployment guide
├── src/bot/              # Bot source code
├── main.py               # Entry point
└── assistants_mode.xml  # Assistant configurations
```

## Next Steps After Deployment

1. **Test the bot** by messaging it on Telegram
2. **Monitor logs** for any issues
3. **Set up monitoring** and alerts
4. **Consider database backup** strategy
5. **Plan for scaling** if needed

## Support

- **Heroku Documentation**: https://devcenter.heroku.com/
- **Heroku CLI Reference**: https://devcenter.heroku.com/articles/heroku-cli-commands
- **Docker Documentation**: https://docs.docker.com/
- **Bot Logs**: Use `heroku logs --tail -a your-app-name` for debugging