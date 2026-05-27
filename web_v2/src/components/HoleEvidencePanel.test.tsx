import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { HoleEvidencePanel, type HoleEvidenceState } from './HoleEvidencePanel'

const readyState: HoleEvidenceState = {
  status: 'ready',
  sourceRef: '900001:7',
  evidence: {
    schema: 'ai-caddie-geometry-evidence-v1',
    globalId: 31795,
    localHole: 7,
    coverage: 'ready',
    hasHazards: true,
    hasMeshes: true,
    sourceRef: '900001:7',
    shotRoutes: [{ shotRef: '900001:7:0', club: '7I', distance: 144, surface: 'green' }],
    surfaceClassifications: [{ shotRef: '900001:7:0', surface: { kind: 'green', source: 'mesh', id: 'green' } }],
    routeEvidence: {
      routeLength_m: 182,
      landingWindowLocal: { center: [0, 182], radius_m: 18 },
      hazardClearances: [
        { hazardId: 'water_crossing', kind: 'water', carryToFront_m: 90, carryToClear_m: 110 },
        { hazardId: 'fairway_bunker', kind: 'bunker', carryToFront_m: 136, carryToClear_m: 150 },
      ],
      landingWindowRisks: [
        { hazardId: 'fairway_bunker', kind: 'bunker', distanceToCenter_m: 16, landingRadius_m: 18, overlap_m: 2 },
        { hazardId: 'right_bunker', kind: 'bunker', distanceToCenter_m: 12, landingRadius_m: 18, overlap_m: 6 },
      ],
      avoidZones: [
        { id: 'fairway_bunker', kind: 'bunker', carryToClear_m: 150 },
        { id: 'right_bunker', kind: 'bunker', distanceToCenter_m: 12, source: 'landing_window' },
      ],
    },
    evidence: [{ label: 'hazards', ref: 'output/prodgeometry_hazards/gid31795_h07_hazards.json' }],
    missingData: [],
  },
  map: {
    schema: 'ai-caddie-hole-map-v1',
    globalId: 31795,
    localHole: 7,
    provider: { name: 'esri_world_imagery', label: 'Esri World Imagery', coordinateSystem: 'WGS84' },
    coverage: 'ready',
    layers: ['hazard', 'target'],
    featureCollection: {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: {
            type: 'Polygon',
            coordinates: [
              [
                [114.162, 22.279],
                [114.163, 22.279],
                [114.163, 22.28],
                [114.162, 22.279],
              ],
            ],
          },
          properties: { layer: 'hazard', kind: 'water', id: 'water-left' },
        },
        {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [114.164, 22.281] },
          properties: { layer: 'target', id: 'pin' },
        },
      ],
    },
    missingData: [{ label: 'shot_routes', reason: 'no shot lines in this map DTO' }],
  },
}

describe('HoleEvidencePanel', () => {
  it('renders geometry coverage, WGS84 map layers, feature evidence, and missing data', () => {
    render(<HoleEvidencePanel state={readyState} />)

    expect(screen.getByRole('heading', { name: 'Hole Evidence' })).toBeInTheDocument()
    expect(screen.getByText('31795 H7')).toBeInTheDocument()
    expect(screen.getByText('ready coverage')).toHaveClass('quality-good')
    expect(screen.getByText('Esri World Imagery')).toBeInTheDocument()
    expect(screen.getByText('WGS84')).toBeInTheDocument()
    const layers = screen.getByLabelText('Geometry layers')
    expect(within(layers).getByText('hazard')).toBeInTheDocument()
    expect(within(layers).getByText('target')).toBeInTheDocument()
    expect(screen.getByText('2 features')).toBeInTheDocument()
    expect(screen.getByText('water-left')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Shot Routes' })).toBeInTheDocument()
    expect(screen.getAllByText('900001:7:0').length).toBeGreaterThan(0)
    expect(screen.getByText('7I 144m green')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Surface Classifications' })).toBeInTheDocument()
    expect(screen.getByText('green / mesh')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Route Evidence' })).toBeInTheDocument()
    expect(screen.getByText('route length 182m')).toBeInTheDocument()
    expect(screen.getByText('landing window [0, 182] r=18m')).toBeInTheDocument()
    expect(screen.getByText('water_crossing')).toBeInTheDocument()
    expect(screen.getByText('water clear 110m')).toBeInTheDocument()
    expect(screen.getAllByText('fairway_bunker').length).toBeGreaterThan(0)
    expect(screen.getAllByText('bunker clear 150m').length).toBeGreaterThan(0)
    expect(screen.getByText('Landing Risks')).toBeInTheDocument()
    expect(screen.getByText('fairway_bunker landing')).toBeInTheDocument()
    expect(screen.getByText('bunker landing 16m from center, overlap 2m, r=18m')).toBeInTheDocument()
    expect(screen.getByText('right_bunker')).toBeInTheDocument()
    expect(screen.getByText('bunker landing 12m from center')).toBeInTheDocument()
    expect(screen.getByText('hazards')).toBeInTheDocument()
    expect(screen.getByText('output/prodgeometry_hazards/gid31795_h07_hazards.json')).toBeInTheDocument()
    expect(screen.getByText('shot_routes')).toBeInTheDocument()
    expect(screen.getByText('no shot lines in this map DTO')).toBeInTheDocument()
    expect(screen.getByLabelText('Hole geometry map')).toBeInTheDocument()
  })

  it('renders loading, idle, and error states', () => {
    const { rerender } = render(<HoleEvidencePanel state={{ status: 'idle' }} />)
    expect(screen.getByText('Select a hole or shot source to load geometry evidence.')).toBeInTheDocument()

    rerender(<HoleEvidencePanel state={{ status: 'loading', sourceRef: '900001:7' }} />)
    expect(screen.getByText('Loading geometry evidence for 900001:7')).toBeInTheDocument()

    rerender(<HoleEvidencePanel state={{ status: 'error', sourceRef: '900001:7', message: 'geometry failed' }} />)
    expect(screen.getByText('geometry failed')).toBeInTheDocument()
  })

  it('offers geometry remediation for partial evidence', async () => {
    const onEnsureGeometry = vi.fn()
    const partialState: HoleEvidenceState = {
      ...readyState,
      evidence: {
        ...readyState.evidence,
        coverage: 'partial',
        hasMeshes: false,
        missingData: [{ label: 'meshes', reason: 'prodgeometry mesh file missing' }],
      },
    }

    const { rerender } = render(
      <HoleEvidencePanel state={partialState} ensureState="idle" onEnsureGeometry={onEnsureGeometry} />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Fetch geometry for 31795 H7' }))

    expect(onEnsureGeometry).toHaveBeenCalledWith({ globalId: 31795, localHole: 7, sourceRef: '900001:7' })

    rerender(<HoleEvidencePanel state={partialState} ensureState="running" onEnsureGeometry={onEnsureGeometry} />)

    expect(screen.getByRole('button', { name: 'Fetching geometry for 31795 H7' })).toBeDisabled()
  })

  it('does not offer geometry remediation when coverage is ready with non-geometry missing data', () => {
    render(
      <HoleEvidencePanel
        state={{
          ...readyState,
          evidence: {
            ...readyState.evidence,
            coverage: 'ready',
            missingData: [{ label: 'shot_routes', reason: 'no source shots for this hole' }],
          },
        }}
        onEnsureGeometry={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Fetch geometry for 31795 H7' })).not.toBeInTheDocument()
    expect(screen.getByText('no source shots for this hole')).toBeInTheDocument()
  })
})
