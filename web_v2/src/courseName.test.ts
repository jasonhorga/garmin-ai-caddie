import { describe, expect, it } from 'vitest'
import {
  canonicalCourseName,
  canonicalCourseVenueName,
  courseSegmentName,
  displayCourseName,
  physicalCourseName,
} from './courseName'

const garmin = 'garmin_scorecard_snapshot'

describe('backend course-name contract', () => {
  it('uses the Garmin snapshot venue with the provider single-loop label', () => {
    const row = {
      name: 'West Park Golf & Country Club ~ West',
      venueName: '西郊高尔夫俱乐部',
      venueNameSource: garmin,
      segmentLabel: 'West',
    }

    expect(canonicalCourseName(row)).toBe('西郊高尔夫俱乐部')
    expect(canonicalCourseVenueName(row)).toBe('西郊高尔夫俱乐部')
    expect(physicalCourseName(row)).toBe('西郊高尔夫俱乐部')
    expect(displayCourseName(row)).toBe('西郊高尔夫俱乐部')
    expect(courseSegmentName(row)).toBe('West')
  })

  it('keeps a backend venue title identical when the loop is separate metadata', () => {
    const row = {
      name: '西郊高尔夫俱乐部',
      segmentLabel: 'West',
    }
    expect(displayCourseName(row)).toBe('西郊高尔夫俱乐部')
    expect(physicalCourseName(row)).toBe('西郊高尔夫俱乐部')
    expect(courseSegmentName(row)).toBe('West')
  })

  it.each(['A/C', 'A+B', 'AB', 'AC', 'AF', 'ABC'])('removes composite route %s from a venue title', (route) => {
    const row = {
      name: `Black Knight ${route}`,
      venueName: '北京天竺黑骑士球员俱乐部',
      venueNameSource: garmin,
      segmentLabel: route,
    }

    expect(displayCourseName(row)).toBe('北京天竺黑骑士球员俱乐部')
    expect(canonicalCourseVenueName(row)).toBe('北京天竺黑骑士球员俱乐部')
    expect(courseSegmentName(row)).toBeNull()
  })

  it('does not let an unmarked or manual Chinese field rename a provider row', () => {
    const row = {
      name: 'Red Flag Valley Golf Club',
      venueName: '手填中文球场',
      venueNameSource: 'manual',
      segmentLabel: null,
    }

    expect(displayCourseName(row)).toBe('Red Flag Valley Golf Club')
    expect(canonicalCourseName(row)).toBe('Red Flag Valley Golf Club')
  })

  it('does not use an unmarked venue field when the provider name is absent', () => {
    expect(displayCourseName({ venueName: '手填中文球场', venueNameSource: 'manual' })).toBe('未知球场')
  })
})
