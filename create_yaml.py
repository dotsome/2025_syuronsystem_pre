import csv
import yaml
from streamlit_authenticator.utilities.hasher import Hasher

users_csv_path = "password.csv"
config_yaml_path = "config.yaml"

with open(users_csv_path, "r") as f:
    csvreader = csv.DictReader(f)
    users = list(csvreader)

with open(config_yaml_path, "r") as f:
    yaml_data = yaml.safe_load(f)

users_dict = {}
for user in users:
    # 単一パスワードをハッシュ化
    hashed_pw = Hasher.hash(user["password"])
    user["password"] = hashed_pw

    tmp_dict = {
        "name": user["name"],
        "password": hashed_pw,
        "email": user["email"],
    }
    users_dict[user["id"]] = tmp_dict

yaml_data["credentials"]["usernames"] = users_dict
with open(config_yaml_path, "w") as f:
    yaml.dump(yaml_data, f)

print("完了")
