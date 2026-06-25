import { render, screen } from '@testing-library/react';
import { RaceCard } from './RaceCard';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';

describe('RaceCard', () => {
  it('renders race details correctly', () => {
    const mockRace = {
      id: 1,
      race_date: '2026-06-25',
      track: 'SEOUL',
      race_number: 5,
      race_name: 'Test Race',
      post_time: '2026-06-25T14:00:00Z',
      distance: 1200,
      surface: 'Sand',
      weather: 'Clear',
      track_condition: 'Dry',
      grade: 'Class 5',
      class_level: '5',
      field_size: 12
    };

    render(
      <BrowserRouter>
        <RaceCard race={mockRace} />
      </BrowserRouter>
    );

    expect(screen.getByText(/Test Race/i)).toBeDefined();
    expect(screen.getByText(/SEOUL/i)).toBeDefined();
  });
});
