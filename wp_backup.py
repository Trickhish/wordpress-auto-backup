import argparse
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import mysql.connector
import re
import subprocess
import datetime
import shutil
import unicodedata
import zipfile
import fnmatch
import time

USUAL_ROOT_DIRS = [ # Path, max searching depth
    ["/home", 2],
    ["/var/www", 3],
    ["/usr/share/nginx/html/", 3],
    ["/opt/lampp/htdocs/", 3],
    ["/srv/www/htdocs/", 3]
]
WP_FILES = ["wp-admin","wp-content","wp-includes","wp-login.php","wp-load.php","wp-config.php","wp-settings.php"]
TEMP_BACKUP_DIR = "/tmp/trickish_wp_backup"
WP_TO_EXCLUDE = [
    # Cache directories
    "*/cache/*",
    "*/wp-content/cache/*",
    "*/wp-content/uploads/cache/*",
    
    # Temporary files
    "*.tmp",
    "*.temp",
    "*~",
    "*.log",
    
    # Version control
    ".git/*",
    ".svn/*",
    ".hg/*",
    
    # WordPress specific
    #"wp-config-sample.php",
    "readme.html",
    "license.txt",
    
    # Backup files (avoid backing up old backups)
    "*.sql",
    "*.sql.gz",
    #"*backup*",
    
    # Large media cache (optional)
    "*/wp-content/uploads/*/thumbnails/*",
    
    # Plugin caches
    "*/wp-content/plugins/*/cache/*",
    "*/wp-rocket/*",
    "*/wp-fastest-cache/*"
]

def isWp(path):
    nn=0
    for ff in WP_FILES:
        if os.path.isfile(os.path.join(path, ff)):
            nn+=1
            if nn > 3:
                return(True)
    return(False)

def _findWpInstalls(args):
    directory, max_depth = args
    found = []
    
    try:
        if not os.path.isdir(directory):
            return found
        
        if isWp(directory):
            found.append(directory)
            return(found)
        
        if max_depth<=0:
            return(found)
        
        for item in os.listdir(directory):
            child = os.path.join(directory, item)
            if os.path.isdir(child):
                sub_results = _findWpInstalls((child, max_depth-1))
                found.extend(sub_results)
                    
    except (OSError, PermissionError, FileNotFoundError):
        pass
    
    return(found)

def findWpInstalls(paths=USUAL_ROOT_DIRS, max_workers=4):
    found=[]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        tasks = {
            executor.submit(_findWpInstalls, args): args[0] 
            for args in paths
        }
        
        for future in as_completed(tasks):
            try:
                results = future.result()
                if results:
                    found.extend(results)
            except Exception as e:
                print(f"Erreur lors de la recherche dans {tasks[future]}: {e}")
    
    return(found)

def getWpDb(wpi):
    if not os.path.isdir(wpi):
        print(f"Invalid wordpress install")
        return(None)
    
    conf_file = os.path.join(wpi, "wp-config.php")

    if not os.path.isfile(conf_file):
        print(f"No config file found")
        return(None)
    
    try:
        with open(conf_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
    except FileNotFoundError:
        print(f"Erreur : Fichier {f} non trouvé")
        return None
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier : {e}")
        return None
    
    db_config = {}
    
    patterns = {
        'DB_NAME': r"define\s*\(\s*['\"]DB_NAME['\"]\s*,\s*['\"]([^'\"]+)['\"]",
        'DB_USER': r"define\s*\(\s*['\"]DB_USER['\"]\s*,\s*['\"]([^'\"]+)['\"]", 
        'DB_PASSWORD': r"define\s*\(\s*['\"]DB_PASSWORD['\"]\s*,\s*['\"]([^'\"]*)['\"]",
        'DB_HOST': r"define\s*\(\s*['\"]DB_HOST['\"]\s*,\s*['\"]([^'\"]+)['\"]",
        'DB_CHARSET': r"define\s*\(\s*['\"]DB_CHARSET['\"]\s*,\s*['\"]([^'\"]+)['\"]"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            db_config[key] = match.group(1)
        else:
            db_config[key] = None
        
    if db_config["DB_HOST"]==None:
        db_config["DB_HOST"] = "localhost"
    
    if any([db_config[key]==None for key in ["DB_NAME","DB_USER","DB_PASSWORD"]]):
        print(f"The database configuration is incomplete")
        return(None)
    
    return(db_config)



def getWpInfo(wpcf):
    # DB_HOST, DB_NAME, DB_USER, DB_PASSWORD
    connection = mysql.connector.connect(
        host=wpcf["DB_HOST"],
        user=wpcf["DB_USER"],
        password=wpcf["DB_PASSWORD"],
        database=wpcf["DB_NAME"]
    )
    cursor = connection.cursor()

    result={}
    for opt in ['siteurl', 'home', 'blogname', 'blogdescription', 'admin_email', 'template']:
        cursor.execute("SELECT option_value FROM wp_options where option_name=%s", (opt,))
        r = cursor.fetchone()
        if r!=None:
            result[opt] = r[0]
        else:
            result[opt] = ""

    return(result)


def formatBytes(bytes_size, decimal_places=2):   
    if bytes_size == 0:
        return "0 B"
    
    if bytes_size < 0:
        return f"-{formatBytes(-bytes_size, decimal_places)}"
    
    units = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    
    unit_index = 0
    size = float(bytes_size)
    
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.{decimal_places}f} {units[unit_index]}"


def saveWpDb(wpi, wpcf, outdir):
    if not os.path.isdir(wpi):
        print(f"Invalid WP install")
        return(False)
    
    if not os.path.isdir(outdir):
        os.makedirs(outdir, exist_ok=True)
    
    if any([wpcf[key]==None for key in ["DB_HOST","DB_USER","DB_PASSWORD","DB_NAME"]]):
        print(f"Invalid database config")
        return(False)

    result = subprocess.run(['mysqldump', '--version'], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        print("❌ Erreur : mysqldump n'est pas installé ou accessible")
        return(False)

    print(f"    🧮 Saving database '{wpcf['DB_NAME']}'")

    cmd = [
        'mysqldump',
        f'--host={wpcf["DB_HOST"]}',
        f'--user={wpcf["DB_USER"]}',
        f'--password={wpcf["DB_PASSWORD"]}',
        '--single-transaction',
        '--routines',
        '--triggers',
        #'--add-drop-database', # Delete the DB if it exists
        '--databases',
        wpcf["DB_NAME"]
    ]

    outfile = os.path.join(outdir, f"{wpcf['DB_NAME']}_backup.sql")

    with open(outfile, 'w', encoding='utf-8') as f:
        result = subprocess.run(
            cmd,
            stdout=f,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3600,
            check=False
        )

    if result.returncode == 0:
        file_size = os.path.getsize(outfile)
        if file_size > 0:
            print(f"    ✅ Database saved : {outfile} ({formatBytes(file_size)})")
            return True
        else:
            print(f"    ❌ Error: Empty backup")
            return False


    return(True)


def matches(file): 
    for pattern in WP_TO_EXCLUDE:
        if fnmatch.fnmatch(file, pattern):
            return True
    return False

def saveWpFiles(wpi, backupdir):
    if not os.path.isdir(wpi):
        print(f"Invalid WP install")
        return(False)
    
    outdir = os.path.join(backupdir, "wordpress")
    if not os.path.isdir(outdir):
        os.makedirs(outdir, exist_ok=True)
    
    # WP_TO_EXCLUDE

    wp_root = Path(wpi).resolve()
    total_files = 0
    skipped_files = 0
    total_size = 0

    copies = []

    print(f"    📁 Saving files")

    print(f"        Filtering relevant files...")

    lt = time.time()

    for root, dirs, files in os.walk(wpi):
        rel_root = os.path.relpath(root, wpi)
        
        #dirs[:] = [d for d in dirs if not any([fnmatch.fnmatch(os.path.join(root, d), pattern) for pattern in WP_TO_EXCLUDE])]
        dirs[:] = [d for d in dirs if not matches(os.path.join(root, d))]

        if rel_root != ".":
            backup_subdir = os.path.join(outdir, rel_root)
            os.makedirs(backup_subdir, exist_ok=True)
        
        for file in files:
            source_file = os.path.join(root, file)
            
            if matches(source_file):
                skipped_files += 1
                #print(f"Skipping {source_file}")
                continue
            
            if not os.path.exists(source_file):
                skipped_files += 1
                continue
            
            try:
                # Calculate destination path
                rel_file_path = os.path.relpath(source_file, wpi)
                dest_file = os.path.join(outdir, rel_file_path)
                
                # Ensure destination directory exists
                dest_dir = os.path.dirname(dest_file)
                os.makedirs(dest_dir, exist_ok=True)
                
                # Copy file with metadata preservation
                copies.append((source_file, dest_file))
                #shutil.copy2(source_file, dest_file)
                #print(f"{source_file} -> {dest_file}")
                
                total_files += 1
                
                
                # Progress indicator for large backups
                ct = time.time()
                if (ct-lt)>0.25:
                    lt=ct
                    print(f"\r       🗃️ {total_files} files to copy...  ", end='', flush=True)
                    
            except (OSError, PermissionError) as e:
                print(f"   ⚠️  Skipped {source_file}: {e}")
                skipped_files += 1
                continue
    
    print(f"\r       🗃️ {total_files} files to copy...  ", end='\n', flush=True)

    lt = time.time()
    tt = len(copies)
    crt=0
    for (src, dest) in copies:
        shutil.copy2(src, dest)
        #print(f"{src} -> {dest}")
        total_size += os.path.getsize(src)
        ct = time.time()
        if (ct-lt)>0.25:
            lt=ct
            print(f"\r       🚚 Copying files: {round(crt/tt*100, 2)}% ({formatBytes(total_size)})  ", end='', flush=True)
        crt+=1
    
    print(f"\r       🚚 Copying files: 100% ({formatBytes(total_size)})  ", end='\n', flush=True)
    print(f"    ✅ Files saved : ({formatBytes(total_size)})\n")

    return(True)

def formatName(name):
    name = name.lower()
    name = name.replace(" ", "_")
    name = name.replace("http://", "")
    name = name.replace("https://", "")
    name = name.replace("www.", "")
    name = name.replace("/", "-")

    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')

    return(name)

if __name__=="__main__":
    parser = argparse.ArgumentParser(add_help=True)
    #parser.add_argument("--name", help="Nom du projet", required=False, default=None)
    #parser.add_argument("--path", help="Chemin du site WP", required=False, default=None)
    #parser.add_argument("--nodb", "-n", action="store_true", help="Ne crée pas de base de données", required=False, default=False)
    
    args = parser.parse_args()

    print("""\n /$$      /$$ /$$$$$$$        /$$$$$$$                      /$$                          
| $$  /$ | $$| $$__  $$      | $$__  $$                    | $$                          
| $$ /$$$| $$| $$  \ $$      | $$  \ $$  /$$$$$$   /$$$$$$$| $$   /$$ /$$   /$$  /$$$$$$ 
| $$/$$ $$ $$| $$$$$$$/      | $$$$$$$  |____  $$ /$$_____/| $$  /$$/| $$  | $$ /$$__  $$
| $$$$_  $$$$| $$____/       | $$__  $$  /$$$$$$$| $$      | $$$$$$/ | $$  | $$| $$  \ $$
| $$$/ \  $$$| $$            | $$  \ $$ /$$__  $$| $$      | $$_  $$ | $$  | $$| $$  | $$
| $$/   \  $$| $$            | $$$$$$$/|  $$$$$$$|  $$$$$$$| $$ \  $$|  $$$$$$/| $$$$$$$/
|__/     \__/|__/            |_______/  \_______/ \_______/|__/  \__/ \______/ | $$____/ 
                                                                               | $$      
                                                                               | $$      
                                                                               |__/      """)
    #print(f"Args: {vars(args)}\n")

    wpil = findWpInstalls()
    
    os.makedirs(TEMP_BACKUP_DIR, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%d-%m-%Y_%-H-%M")

    print(f"🏗️ Found {len(wpil)} wordpress installs")

    for wpi in wpil:
        wpin = os.path.basename(os.path.normpath(wpi))
        wpcf = getWpDb(wpi) # DB_HOST, DB_NAME, DB_USER, DB_PASSWORD
        if wpcf==None:
            print(f"    Skipping backup")
            continue
        
        wpdt = getWpInfo(wpcf)
        # 'siteurl', 'home', 'blogname', 'blogdescription', 'admin_email', 'template'

        print(f"\n💾 Creating a backup of '{wpdt['blogname']}' ({wpi})")

        fmname = wpdt["blogname"] if wpdt["blogname"]!=None else (wpdt['siteurl'] if wpdt['siteurl']!=None else wpi)
        fmname = formatName(fmname)
        outdir = os.path.join(TEMP_BACKUP_DIR, f"backup_{fmname}_{timestamp}")

        r = saveWpFiles(wpi, outdir)
        if r==False:
            print(f"")
            exit()

        r = saveWpDb(wpi, wpcf, outdir)
        if r==False:
            print(f"")
            exit()
    
    print("")

