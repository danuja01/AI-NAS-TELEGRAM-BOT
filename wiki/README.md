# GitHub Wiki Documentation - Deployment Instructions

This directory contains complete GitHub Wiki documentation for the NAS Telegram AI Assistant.

## Wiki Structure

All 19 wiki pages have been created:

### Core Documentation
1. **Home.md** - Landing page with quick start
2. **Installation.md** - Detailed bare metal setup
3. **Docker-Deployment.md** - Docker deployment guide
4. **Configuration-Guide.md** - Complete .env reference
5. **Commands-Reference.md** - All commands categorized
6. **API-Setup.md** - Getting all required API keys

### Feature Guides
7. **AI-and-RAG.md** - AI capabilities and RAG system
8. **System-Monitoring.md** - Monitoring features
9. **Docker-Management.md** - Container operations
10. **File-Management.md** - File operations and security
11. **Root-Access-and-SSH.md** - Elevated access features

### Configuration & Help
12. **Security.md** - Best practices and security model
13. **Troubleshooting.md** - Common issues and solutions
14. **FAQ.md** - Frequently asked questions

### Reference
15. **Architecture.md** - System design and diagrams
16. **Development-and-Contributing.md** - For contributors
17. **Deployment-Options.md** - Production strategies

### Special Files
18. **_Sidebar.md** - Navigation menu
19. **_Footer.md** - Page footer

## How to Deploy to GitHub Wiki

### Method 1: GitHub Web Interface

1. **Enable Wiki on GitHub**:
   - Go to your repository on GitHub
   - Click Settings
   - Scroll to Features section
   - Check "Wikis" checkbox

2. **Create Pages One by One**:
   - Click "Wiki" tab in your repository
   - Click "Create the first page" or "New Page"
   - Copy content from each .md file here
   - Save each page

   **Order**:
   - Start with Home.md (becomes the wiki homepage)
   - Then create other pages in any order
   - Create _Sidebar.md and _Footer.md last

### Method 2: Git Clone (Recommended - Faster)

1. **Enable Wiki** (same as Method 1)

2. **Clone Wiki Repository**:
   ```bash
   # Get the wiki clone URL from the Wiki tab
   git clone https://github.com/your-username/your-repo.wiki.git
   cd your-repo.wiki
   ```

3. **Copy All Files**:
   ```bash
   cp /path/to/BOT/wiki/*.md .
   ```

4. **Commit and Push**:
   ```bash
   git add .
   git commit -m "Add comprehensive wiki documentation"
   git push
   ```

5. **Verify**:
   - Go to your repository's Wiki tab
   - All pages should now appear
   - Sidebar navigation should work
   - Footer should appear on all pages

### Method 3: Script (Fastest)

Create a deployment script:

```bash
#!/bin/bash
# deploy-wiki.sh

REPO_URL="https://github.com/your-username/your-repo.wiki.git"
WIKI_DIR="/tmp/wiki-deploy"

# Clone wiki
git clone $REPO_URL $WIKI_DIR
cd $WIKI_DIR

# Copy all markdown files
cp /path/to/BOT/wiki/*.md .

# Commit and push
git add .
git commit -m "Update wiki documentation - $(date +%Y-%m-%d)"
git push

# Cleanup
cd ..
rm -rf $WIKI_DIR

echo "Wiki deployed successfully!"
```

Run it:
```bash
chmod +x deploy-wiki.sh
./deploy-wiki.sh
```

## Customization

### Before Deploying

1. **Update Repository Links**:
   - Open `_Sidebar.md` and `_Footer.md`
   - Replace `https://github.com/your-repo` with your actual repo URL

2. **Add Your Repository Name**:
   - Search all .md files for `<your-repo-url>`
   - Replace with actual repository URL

3. **Optional - Add Screenshots**:
   - Take screenshots of your bot in action
   - Upload to GitHub (Issues or wiki itself)
   - Add to Home.md and other pages

### After Deploying

1. **Test Navigation**:
   - Click through all wiki links
   - Verify sidebar appears on all pages
   - Check footer links work

2. **Update Main README**:
   Add wiki link to your main repository README.md:
   ```markdown
   ## Documentation

   📚 **[Complete Documentation Wiki](https://github.com/your-username/your-repo/wiki)**

   - [Installation Guide](wiki/Installation)
   - [Docker Deployment](wiki/Docker-Deployment)
   - [Commands Reference](wiki/Commands-Reference)
   - [API Setup](wiki/API-Setup)
   ```

## Maintenance

### Updating Documentation

1. Edit files in `BOT/wiki/` directory
2. Re-run deployment method (git push or manual update)
3. Verify changes on GitHub wiki

### Keep in Sync

When you:
- Add new features → Update relevant wiki pages
- Fix bugs → Update Troubleshooting.md
- Change configuration → Update Configuration-Guide.md
- Add commands → Update Commands-Reference.md

## Wiki Features

### Internal Links

Use this format for linking between pages:
```markdown
[[Page Name]]
[[Page Title|Page-File-Name]]
```

Examples in the wiki:
- `[[Home]]` - Links to Home page
- `[[Docker Deployment|Docker-Deployment]]` - Custom text

### External Links

Standard markdown:
```markdown
[Link Text](https://example.com)
```

### Sidebar Navigation

The `_Sidebar.md` provides navigation on every page. Edit it to:
- Add new pages
- Reorganize sections
- Add external links

### Search

GitHub wiki has built-in search. Users can search all wiki content.

## Quality Checklist

Before making wiki public:

- [ ] All internal links work
- [ ] Repository URLs updated
- [ ] Code examples tested
- [ ] Screenshots added (optional)
- [ ] Sidebar navigation complete
- [ ] Footer links work
- [ ] No placeholder text
- [ ] Consistent formatting
- [ ] Table of contents accurate

## Need Help?

- [GitHub Wiki Documentation](https://docs.github.com/en/communities/documenting-your-project-with-wikis)
- [Markdown Guide](https://www.markdownguide.org/)

---

**Ready to deploy!** Choose your method above and make your documentation public.
