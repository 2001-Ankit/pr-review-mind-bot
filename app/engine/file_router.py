class FileRouter:
    MAX_FILE_CHANGES = 200

    def should_split(self, file_change):
        total = file_change.total_added + file_change.total_removed
        return total > self.MAX_FILE_CHANGES