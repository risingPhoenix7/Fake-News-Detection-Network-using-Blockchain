import requests
import uuid

class IPFSHandler:

    base_url = "https://api.web3.storage"
    auth = {
        "Authorization":"Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkaWQ6ZXRocjoweDk0Nzk1MzBmMTFkMmI0MWE5NTFlNjA0NjhlN0M5OTc3ZmVCYjQ2QTgiLCJpc3MiOiJ3ZWIzLXN0b3JhZ2UiLCJpYXQiOjE2OTc1Nzc4MTkzOTYsIm5hbWUiOiJibG9ja2NoYWlucHJvamVjdCJ9.ibPZ2NWkxew2CwI0xfL3-RIq4ctds95RIexDk__uL_U"
    }

    @staticmethod
    def put_to_ipfs(content):
        # putting data to IPFS and returns a ipfs address
        url = f"{IPFSHandler.base_url}/upload"
        files = {"file": content}

        try:
            res = requests.post(url, files=files, headers=IPFSHandler.auth)
        except Exception as e:
            print(e)
            return ""
        
        try:
            print(res.json())
            ipfs_address = res.json()["cid"]
        except Exception as e:
            print("Error: ", e)
            return ""
        
        return ipfs_address
  

    @staticmethod
    def get_from_ipfs(ipfs_address):
        # fetching from IPFS and returns data
        try:
            res = requests.get(f"https://{ipfs_address}.ipfs.dweb.link", headers=IPFSHandler.auth)
        except Exception as e:
            print(e)
            return ""
        
        # filename = f"article_{uuid.uuid4()}.txt"
        # with open(f"{filename}", "w") as f:
        #     f.write(res.content.decode("utf-8"))

        return res.text
    

if __name__=="__main__":
    # testing
    ipfs_address = 'bafkreig5stfj2plvltwxi7cl3hbknde2a2nyuf5kpheinzkcmiid43mutq'
    print(ipfs_address)
    print(IPFSHandler.get_from_ipfs(ipfs_address))
