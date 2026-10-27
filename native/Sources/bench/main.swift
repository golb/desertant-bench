import Foundation
import Voz
import Who
import Ear
@_spi(ClearBindings) import Clear
@_spi(GistBindings) import Gist

// One process per model: load once (timed separately), then every input
// `passes` times. Repeat 0 is the first call after load; the rest are warm.
struct Request: Decodable {
    let model: String
    let cacheRoot: String
    let inputs: [Input]
    let passes: Int?
}
struct Input: Decodable { let id: String; let text: String?; let file: String?; let output: String? }

func ms(_ start: ContinuousClock.Instant) -> Double {
    let d = start.duration(to: .now).components
    return Double(d.seconds) * 1000 + Double(d.attoseconds) / 1e15
}
func need<T>(_ value: T?, _ what: String) throws -> T {
    guard let value else { throw NSError(domain: "\(what)_required", code: 1) }
    return value
}

@main struct Main {
    static func main() async {
        do {
            guard CommandLine.arguments.count == 2 else { throw NSError(domain: "usage: bench REQUEST.json", code: 1) }
            let request = try JSONDecoder().decode(Request.self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
            let passes = request.passes ?? 1
            guard (1...10).contains(passes) else { throw NSError(domain: "invalid_passes", code: 1) }
            var rows: [[String: Any]] = []
            var meta: [String: Any] = [:]
            func each(_ body: (Input, Int) async throws -> [String: Any]) async throws {
                for input in request.inputs {
                    for r in 0..<passes {
                        let tick = ContinuousClock.now
                        var row = try await body(input, r)
                        row["inferenceMs"] = row["inferenceMs"] ?? ms(tick)
                        row["id"] = input.id; row["repeat"] = r
                        rows.append(row)
                    }
                }
            }
            let start = ContinuousClock.now
            switch request.model {
            case "voz":
                meta["initiallyDownloaded"] = Voz.isDownloaded(cacheRoot: request.cacheRoot)
                let voz = try await Voz(cacheRoot: request.cacheRoot)
                meta["loadMs"] = ms(start); meta["revision"] = VozModel.revision
                try await each { input, _ in
                    let tick = ContinuousClock.now
                    let result = try await voz.transcribe(path: try need(input.file, "file"))
                    return ["callMs": ms(tick), "inferenceMs": result.processingTime * 1000,
                            "durationSeconds": result.duration, "text": result.text]
                }
            case "who":
                let who = Who(directory: nil, cacheRoot: request.cacheRoot)
                meta["initiallyDownloaded"] = who.isDownloaded()
                try await who.download(); meta["loadMs"] = ms(start)
                try await each { input, _ in
                    let result = try await who.diarize(contentsOf: URL(fileURLWithPath: try need(input.file, "file")))
                    return ["speakerCount": result.speakerCount,
                            "turns": result.turns.map { ["start": $0.start, "end": $0.end, "speaker": $0.speaker] }]
                }
            case "ear":
                let ear = Ear(directory: nil, cacheRoot: request.cacheRoot)
                meta["initiallyDownloaded"] = ear.isDownloaded()
                try await ear.download(); meta["loadMs"] = ms(start); meta["revision"] = EarModel.revision
                try await each { input, _ in
                    let result = try await ear.identify(path: try need(input.file, "file"))
                    return ["language": result.language ?? "", "confidence": result.confidence,
                            "reliable": result.isReliable,
                            "candidates": result.candidates.prefix(3).map { ["language": $0.language, "probability": $0.probability] }]
                }
            case "clear":
                let clear = Clear(directory: nil, cacheRoot: request.cacheRoot)
                meta["initiallyDownloaded"] = clear.isDownloaded()
                try await clear.download(); meta["loadMs"] = ms(start); meta["revision"] = ClearModel.revision
                // Enhancement only: loudness mastering would confound ASR.
                let options = Clear.Options(mastering: .bypass, sampleRate: 16_000)
                try await each { input, _ in
                    let file = try need(input.file, "file"), output = try need(input.output, "output")
                    guard file != output else { throw NSError(domain: "separate_output_required", code: 1) }
                    let result = try await clear.enhance(path: file, to: output, options: options)
                    return ["requestedSampleRate": options.sampleRate, "reportedSampleRate": result.sampleRate,
                            "durationSeconds": result.durationSec]
                }
            case "gist":
                let gist = Gist(directory: nil, cacheRoot: request.cacheRoot)
                meta["initiallyDownloaded"] = gist.isDownloaded()
                try await gist.download(); meta["loadMs"] = ms(start); meta["revision"] = GistModel.revision
                try await each { input, _ in
                    let topics = try await gist.classify(try need(input.text, "text"), topK: 3, threshold: 0)
                    return ["topics": topics.map { ["slug": $0.slug, "score": $0.score] }]
                }
            default: throw NSError(domain: "unknown_model", code: 1)
            }
            meta["model"] = request.model; meta["sdk"] = "4.1.0"; meta["rows"] = rows
            FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: meta, options: [.sortedKeys]))
        } catch {
            FileHandle.standardError.write(Data("bench: \(error)\n".utf8)); exit(1)
        }
    }
}
