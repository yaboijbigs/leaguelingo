import os

def generate_sitemap(start_path='.', output_file='sitemap.txt'):
    with open(output_file, 'w') as f:
        for root, dirs, files in os.walk(start_path):
            level = root.replace(start_path, '').count(os.sep)
            indent = ' ' * 4 * level
            f.write(f'{indent}{os.path.basename(root)}/\n')
            subindent = ' ' * 4 * (level + 1)
            for filename in files:
                f.write(f'{subindent}{filename}\n')

if __name__ == "__main__":
    generate_sitemap()
