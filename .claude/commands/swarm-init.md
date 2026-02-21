Analyze the structure of this repository and build a keyword index for Swarm Lock Manager.

1. Run `find . -type d -maxdepth 3 | grep -v '.git\|.swarm\|__pycache__\|node_modules'` to see the directory tree.
2. Identify at most 20 meaningful domain terms (e.g. "auth", "api", "database"). Each keyword should map to one or more directories or key files.
3. Write the index by running:
   echo '<json>' | swarm write-index
   Where <json> is: {"terms": {"keyword": ["dir/", "file.py"], ...}}

Keep keywords short (1-2 words), lowercase, no punctuation. These become the lock identifiers agents use.
