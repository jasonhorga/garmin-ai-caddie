import SwiftUI

// MARK: - shared options

/// Lie choices for the pickers (value, 中文). Mirrors `shotLieLabel` / the legend.
public let roundEditLieOptions: [(String, String)] = [
    ("fairway", "球道"), ("rough", "长草"), ("bunker", "沙坑"),
    ("water", "水"), ("green", "果岭"), ("teebox", "发球台"),
]

/// Fallback club list when the player's real bag hasn't loaded (the picker prefers the real bag,
/// passed in from the screen). These are choices to pick from — not fabricated shot data.
public let roundEditCommonClubs: [String] = [
    "一号木", "三号木", "五号木", "三号铁", "四号铁", "五号铁", "六号铁",
    "七号铁", "八号铁", "九号铁", "PW", "GW", "SW", "LW", "推杆",
]

// MARK: - edit overlay (handles + tap → add/edit)

/// The edit affordance layer, overlaid on the read-only shot map when editing. Draws a drag handle
/// ring on each landing, and turns a tap into either "edit that shot" (hit a handle) or "add a shot
/// here" (empty). Pixel↔view conversion uses the fitted map size from GeometryReader.
/// (Drag-to-move + magnifier land in a follow-up; this layer is the tap-based core edit loop.)
public struct RoundShotEditLayer: View {
    @ObservedObject var editModel: RoundEditModel
    let overlay: CoursePrepOverlay
    let clubs: [String]

    @State private var editingShot: RoundShot?
    @State private var addAtPx: [Double]?

    public init(editModel: RoundEditModel, overlay: CoursePrepOverlay, clubs: [String]) {
        self.editModel = editModel
        self.overlay = overlay
        self.clubs = clubs
    }

    public var body: some View {
        GeometryReader { geo in
            let sx = geo.size.width / CGFloat(max(overlay.w, 1))
            let sy = geo.size.height / CGFloat(max(overlay.h, 1))
            Canvas { ctx, _ in
                for shot in editModel.map.shots {
                    guard let e = shot.end, e.count >= 2 else { continue }
                    let p = CGPoint(x: CGFloat(e[0]) * sx, y: CGFloat(e[1]) * sy)
                    let r: CGFloat = 11
                    let ring = Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r))
                    ctx.stroke(ring, with: .color(.white), lineWidth: 2)
                    ctx.stroke(ring, with: .color(.black.opacity(0.45)), lineWidth: 0.5)
                }
            }
            .contentShape(Rectangle())
            .gesture(
                SpatialTapGesture().onEnded { v in
                    let loc = v.location
                    if let hit = editModel.map.shots.first(where: { hitTest($0, loc, sx, sy) }) {
                        editingShot = hit
                    } else {
                        addAtPx = [Double(loc.x / sx), Double(loc.y / sy)]
                    }
                }
            )
        }
        .sheet(item: $editingShot) { shot in
            ShotEditSheet(
                shot: shot, clubs: effectiveClubs,
                onClub: { editModel.editClub(shotId: shot.id, $0) },
                onLie: { editModel.editLie(shotId: shot.id, $0) },
                onDelete: { editModel.delete(shotId: shot.id) }
            )
        }
        .sheet(isPresented: Binding(get: { addAtPx != nil }, set: { if !$0 { addAtPx = nil } })) {
            if let px = addAtPx {
                AddShotSheet(clubs: effectiveClubs) { club, lie in
                    editModel.addShot(px: px, club: club, lie: lie, afterShotId: insertAfter(px))
                    addAtPx = nil
                }
            }
        }
    }

    private var effectiveClubs: [String] { clubs.isEmpty ? roundEditCommonClubs : clubs }

    private func hitTest(_ s: RoundShot, _ loc: CGPoint, _ sx: CGFloat, _ sy: CGFloat) -> Bool {
        guard let e = s.end, e.count >= 2 else { return false }
        let p = CGPoint(x: CGFloat(e[0]) * sx, y: CGFloat(e[1]) * sy)
        return hypot(p.x - loc.x, p.y - loc.y) <= 24
    }

    /// Insert the new shot after the existing landing nearest the tap (a sensible "which gap"; the
    /// backend re-sequences by this id). Forward-play assumption keeps the two connecting lines sane.
    private func insertAfter(_ px: [Double]) -> String? {
        editModel.map.shots.min(by: { pxDist($0, px) < pxDist($1, px) })?.id
    }

    private func pxDist(_ s: RoundShot, _ px: [Double]) -> CGFloat {
        guard let e = s.end, e.count >= 2 else { return .greatestFiniteMagnitude }
        return hypot(CGFloat(e[0]) - CGFloat(px[0]), CGFloat(e[1]) - CGFloat(px[1]))
    }
}

// MARK: - edit an existing shot (club / lie / delete)

public struct ShotEditSheet: View {
    let shot: RoundShot
    let clubs: [String]
    let onClub: (String) -> Void
    let onLie: (String) -> Void
    let onDelete: () -> Void
    @Environment(\.dismiss) private var dismiss

    public init(shot: RoundShot, clubs: [String], onClub: @escaping (String) -> Void,
                onLie: @escaping (String) -> Void, onDelete: @escaping () -> Void) {
        self.shot = shot
        self.clubs = clubs
        self.onClub = onClub
        self.onLie = onLie
        self.onDelete = onDelete
    }

    public var body: some View {
        NavigationStack {
            Form {
                Section("球杆") {
                    Picker("球杆", selection: Binding(
                        get: { shot.club ?? "" },
                        set: { if !$0.isEmpty { onClub($0) } })) {
                        Text("未知").tag("")
                        ForEach(clubs, id: \.self) { Text($0).tag($0) }
                    }
                }
                Section("球位(球落哪)") {
                    Picker("球位", selection: Binding(
                        get: { shot.endLie ?? shot.lie ?? "" },
                        set: { if !$0.isEmpty { onLie($0) } })) {
                        Text("—").tag("")
                        ForEach(roundEditLieOptions, id: \.0) { Text($0.1).tag($0.0) }
                    }
                }
                Section {
                    Button(role: .destructive) { onDelete(); dismiss() } label: {
                        Label("删除这一杆", systemImage: "trash")
                    }
                }
            }
            .navigationTitle("改这一杆")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } } }
        }
        .presentationDetents([.medium])
    }
}

// MARK: - add a shot (club default-highlighted by nothing yet; lie)

public struct AddShotSheet: View {
    let clubs: [String]
    let onAdd: (String?, String?) -> Void
    @State private var club: String = ""
    @State private var lie: String = "fairway"
    @Environment(\.dismiss) private var dismiss

    public init(clubs: [String], onAdd: @escaping (String?, String?) -> Void) {
        self.clubs = clubs
        self.onAdd = onAdd
    }

    public var body: some View {
        NavigationStack {
            Form {
                Section("这一杆用什么杆") {
                    Picker("球杆", selection: $club) {
                        Text("未知").tag("")
                        ForEach(clubs, id: \.self) { Text($0).tag($0) }
                    }
                }
                Section("球落哪") {
                    Picker("球位", selection: $lie) {
                        ForEach(roundEditLieOptions, id: \.0) { Text($0.1).tag($0.0) }
                    }
                }
            }
            .navigationTitle("补一杆")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("加上") { onAdd(club.isEmpty ? nil : club, lie.isEmpty ? nil : lie); dismiss() }
                }
            }
        }
        .presentationDetents([.medium])
    }
}

// MARK: - edit-mode content (observes the edit model so optimistic changes redraw)

/// The whole edit-mode body for one hole: the map with the edit overlay + the penalty stepper +
/// a hint. Observes ``RoundEditModel`` so every optimistic change redraws instantly.
public struct RoundShotEditContent: View {
    @ObservedObject var editModel: RoundEditModel
    let topoURL: URL?

    public init(editModel: RoundEditModel, topoURL: URL?) {
        self.editModel = editModel
        self.topoURL = topoURL
    }

    public var body: some View {
        VStack(spacing: 12) {
            RoundShotMapView(shotMap: editModel.map, topoURL: topoURL, editModel: editModel)
            PenaltyStepper(value: editModel.map.manualPenalty) { editModel.setPenalty($0) }
                .hubCard()
            Text("点空白处补一杆 · 点某个落点改球杆/球位/删除")
                .font(.caption).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .center)
            RoundShotMapLegend()
            if let err = editModel.pendingError {
                Text(err).font(.caption2).foregroundStyle(.orange).multilineTextAlignment(.center)
            }
        }
    }
}

// MARK: - per-hole manual penalty stepper

public struct PenaltyStepper: View {
    let value: Int
    let onChange: (Int) -> Void

    public init(value: Int, onChange: @escaping (Int) -> Void) {
        self.value = value
        self.onChange = onChange
    }

    public var body: some View {
        HStack {
            Text("本洞罚杆").font(.subheadline.weight(.medium))
            Spacer()
            Button { onChange(max(0, value - 1)) } label: {
                Image(systemName: "minus.circle.fill").font(.title2)
            }
            .buttonStyle(.plain).foregroundStyle(value > 0 ? Color.accentColor : Color.secondary)
            Text("\(value)").font(.title3.monospacedDigit().weight(.bold)).frame(minWidth: 28)
            Button { onChange(value + 1) } label: {
                Image(systemName: "plus.circle.fill").font(.title2)
            }
            .buttonStyle(.plain).foregroundStyle(Color.accentColor)
        }
        .padding(.vertical, 4)
    }
}
