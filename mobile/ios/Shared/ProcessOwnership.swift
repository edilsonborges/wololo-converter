import Darwin

nonisolated func processIsRunning(_ processID: Int32) -> Bool {
    kill(processID, 0) == 0 || errno == EPERM
}
