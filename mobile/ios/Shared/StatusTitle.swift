import WololoKit

func statusTitle(_ status: LocalDownloadStatus) -> String {
    switch status {
    case .queued: L("Waiting in queue")
    case .processing: L("Preparing your download")
    case .transferring: L("Saving to your iPhone")
    case .readyToSave: L("Ready to save")
    case .saved: L("Saved")
    case .failed: L("Download failed")
    case .cancelled: L("Cancelled")
    }
}
