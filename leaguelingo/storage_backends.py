from storages.backends.s3boto3 import S3Boto3Storage

class CustomS3Boto3Storage(S3Boto3Storage):
    def __init__(self, *args, **kwargs):
        kwargs['default_acl'] = None
        super().__init__(*args, **kwargs)

    def _save(self, name, content):
        self.object_parameters = {}
        return super()._save(name, content)