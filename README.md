# Wordpress Auto Backup

## Introduction

This program aims to automate wordpress installations backups. \
It will automatically find all Wordpress installations and save the files and the database.

## Output example
```
 /$$      /$$ /$$$$$$$        /$$$$$$$                      /$$
| $$  /$ | $$| $$__  $$      | $$__  $$                    | $$
| $$ /$$$| $$| $$  \ $$      | $$  \ $$  /$$$$$$   /$$$$$$$| $$   /$$ /$$   /$$  /$$$$$$
| $$/$$ $$ $$| $$$$$$$/      | $$$$$$$  |____  $$ /$$_____/| $$  /$$/| $$  | $$ /$$__  $$
| $$$$_  $$$$| $$____/       | $$__  $$  /$$$$$$$| $$      | $$$$$$/ | $$  | $$| $$  \ $$
| $$$/ \  $$$| $$            | $$  \ $$ /$$__  $$| $$      | $$_  $$ | $$  | $$| $$  | $$
| $$/   \  $$| $$            | $$$$$$$/|  $$$$$$$|  $$$$$$$| $$ \  $$|  $$$$$$/| $$$$$$$/
|__/     \__/|__/            |_______/  \_______/ \_______/|__/  \__/ \______/ | $$____/
                                                                               | $$
                                                                               | $$
                                                                               |__/
🏗️ Found 2 wordpress installs

💾 Creating a backup of 'Test WP' (/home/wp.dev.dury.dev/public_html)
    📁 Saving files
        Filtering relevant files...
       🗃️ 3231 files to copy...
       🚚 Copying files: 100% (71.46 MB)
    ✅ Files saved : (71.46 MB)

    🧮 Saving database 'wp_inst_test'
    ✅ Database saved : /tmp/trickish_wp_backup/backup_test_wp_27-07-2025_17-42/wp_inst_test_backup.sql (113.49 KB)
```
