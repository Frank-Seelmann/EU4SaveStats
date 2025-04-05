from dotenv import load_dotenv
from pathlib import Path
from app import create_app
import sys

sys.path.append(str(Path(__file__).parent))

env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

app = create_app()

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M:%S'):
    if value is None:
        return ""
    return value.strftime(format)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)