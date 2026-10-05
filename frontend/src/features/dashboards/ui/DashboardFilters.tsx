import { useCallback, useEffect, useState, useRef } from 'react'
import {
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Typography,
  Button,
  Stack,
  Chip,
  Paper,
  Box,
  Alert,
} from '@mui/material'
import { useFilterValues } from '../api/dashboardApi'
import type { FilterDetail } from '../../../shared/types/api.types'

/**
 * Message shown when a declared filter type has no evaluable control.
 *
 * A dashboard that already stores a `range` filter renders no control; silence
 * is the same "does nothing" defect as a dead control, so the panel says so
 * instead. This wording has a single home.
 */
const UNEVALUABLE_FILTER_MESSAGE =
  'has a declared type that is not supported by the filters panel and sends no value'

interface DashboardFiltersProps {
  filters: FilterDetail[]
  values: Record<string, string | string[] | number | number[]>
  onChange: (filters: Record<string, string | string[] | number | number[]>) => void
  onReset?: () => void
  dashboardId: string
}

export function DashboardFilters({
  filters,
  values,
  onChange,
  onReset,
  dashboardId,
}: DashboardFiltersProps) {
  const [localFilters, setLocalFilters] = useState<
    Record<string, string | string[] | number | number[]>
  >(() => values || {})

  // Sync local state when external values prop changes
  // This is required for the filter reset behavior when dashboard data reloads
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLocalFilters(values || {})
  }, [values])

  // Debounce timer ref for filter changes (300ms delay)
  const debounceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleFilterChange = useCallback(
    (filterName: string, value: string | string[] | number | number[]) => {
      const newFilters = { ...localFilters, [filterName]: value }
      setLocalFilters(newFilters)

      // Debounce the parent onChange to avoid re-renders on every keystroke/drag
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current)
      }
      debounceTimeoutRef.current = setTimeout(() => {
        onChange(newFilters)
        debounceTimeoutRef.current = null
      }, 300)
    },
    [localFilters, onChange]
  )

  const handleApplyFilters = useCallback(() => {
    // Clear pending debounce and apply immediately
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current)
      debounceTimeoutRef.current = null
    }
    onChange(localFilters)
  }, [localFilters, onChange])

  const handleResetFilters = useCallback(() => {
    const emptyFilters: Record<string, string | string[] | number | number[]> = {}
    setLocalFilters(emptyFilters)
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current)
      debounceTimeoutRef.current = null
    }
    onChange(emptyFilters)
    onReset?.()
  }, [onChange, onReset])

  if (!filters || filters.length === 0) {
    return null
  }

  return (
    <Paper elevation={0} variant="outlined" sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Filters
      </Typography>
<Stack spacing={2}>
        {filters.map((filter) => (
          <FilterField
            key={filter.id}
            filter={filter}
            value={localFilters[filter.name]}
            onChange={(value) => handleFilterChange(filter.name, value)}
            dashboardId={dashboardId}
          />
        ))}
        <Stack direction="row" spacing={1}>
          <Button variant="contained" onClick={handleApplyFilters} size="small">
            Apply
          </Button>
          <Button variant="outlined" onClick={handleResetFilters} size="small">
            Reset
          </Button>
        </Stack>
      </Stack>
    </Paper>
  )
}

interface FilterFieldProps {
  filter: FilterDetail
  value: string | string[] | number | number[] | undefined
  onChange: (value: string | string[] | number | number[]) => void
  dashboardId: string
}

function FilterField({ filter, value, onChange, dashboardId }: FilterFieldProps) {
  const config = filter.config
  const { data: filterValuesData } = useFilterValues(dashboardId, filter.name)
  const dynamicValues = config.source === 'data' ? (filterValuesData?.values || []) : []
  const options = config.source === 'data'
    ? dynamicValues.map(v => ({ label: v, value: v }))
    : (config.options || [])

  switch (filter.type) {
    case 'select':
      return (
        <FormControl fullWidth size="small">
          <InputLabel>{filter.name}</InputLabel>
          <Select
            value={(value as string) || ''}
            label={filter.name}
            onChange={(e) => onChange(e.target.value)}
          >
            {options.map((opt) => (
              <MenuItem key={opt.value} value={opt.value}>
                {opt.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      )

    case 'multiselect': {
      const selectedValues = Array.isArray(value) ? value : []
      return (
        <FormControl fullWidth size="small">
          <InputLabel>{filter.name}</InputLabel>
          <Select
            multiple
            value={selectedValues}
            label={filter.name}
            onChange={(e) => onChange(e.target.value)}
            renderValue={(selected) => (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {(selected as string[]).map((val) => (
                  <Chip key={val} label={val} size="small" />
                ))}
              </Box>
            )}
          >
            {options.map((opt) => (
              <MenuItem key={opt.value} value={opt.value}>
                {opt.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      )
    }

    case 'date':
      return (
        <TextField
          fullWidth
          size="small"
          label={filter.name}
          type="date"
          value={(value) || ''}
          onChange={(e) => onChange(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
      )

    default:
      return (
        <Alert severity="warning">
          {`Filter "${filter.name}" ${UNEVALUABLE_FILTER_MESSAGE}. Declared type is "${filter.type}".`}
        </Alert>
      )
  }
}