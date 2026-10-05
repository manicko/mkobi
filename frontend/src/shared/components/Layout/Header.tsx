import { AppBar, Box, Button, IconButton, Toolbar, Typography, Menu, MenuItem, Divider } from '@mui/material'
import { useNavigate, useLocation } from 'react-router-dom'
import { useState } from 'react'
import { useAuthIdentity } from '../../auth/identity'
import { logout } from '../../auth/actions'
import AccountCircle from '@mui/icons-material/AccountCircle'
import LogoutIcon from '@mui/icons-material/Logout'
import Settings from '@mui/icons-material/Settings'

interface NavItem {
  label: string
  path: string
  roles?: string[]
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboards', path: '/dashboards' },
  { label: 'Admin', path: '/admin', roles: ['admin'] },
]

export function Header() {
  const { user } = useAuthIdentity()
  const navigate = useNavigate()
  const location = useLocation()
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)

  const handleNavigation = (path: string) => {
    void navigate(path)
  }

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleMenuClose = () => {
    setAnchorEl(null)
  }

  const handleLogout = () => {
    handleMenuClose()
    void logout()
    void navigate('/login')
  }

  const isActive = (path: string) => {
    return location.pathname === path || (path === '/dashboards' && location.pathname.startsWith('/dashboard'))
  }

  return (
    <AppBar position="static">
      <Toolbar>
        <Typography variant="h6" component="div" sx={{ mr: 4 }}>
          MKOBI Dashboard
        </Typography>

        {user && (
          <Box sx={{ display: 'flex', flexGrow: 1 }}>
            {NAV_ITEMS.filter(item => !item.roles || item.roles.includes(user.role)).map(item => (
              <Button
                key={item.path}
                onClick={() => handleNavigation(item.path)}
                sx={{
                  mr: 1,
                  color: isActive(item.path) ? '#fff' : 'rgba(255, 255, 255, 0.75)',
                  fontWeight: isActive(item.path) ? 600 : 400,
                  borderBottom: isActive(item.path) ? '2px solid #fff' : 'none',
                  borderRadius: 0,
                  transition: 'color 200ms ease, border-bottom-color 200ms ease',
                  ...(!isActive(item.path) && {
                    '&:hover': {
                      color: 'rgba(255, 255, 255, 0.9)',
                      borderBottom: '1px solid rgba(255, 255, 255, 0.3)',
                    },
                  }),
                }}
              >
                {item.label}
              </Button>
            ))}
          </Box>
        )}

        {user && (
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Typography variant="body2" sx={{ mr: 1 }}>
              {user.email}
            </Typography>
            <IconButton color="inherit" onClick={handleMenuOpen}>
              <AccountCircle />
            </IconButton>
            <Menu
              anchorEl={anchorEl}
              open={Boolean(anchorEl)}
              onClose={handleMenuClose}
              anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
              transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            >
              <MenuItem onClick={() => { handleMenuClose(); void navigate('/profile') }}>
                <Settings sx={{ mr: 1, fontSize: 20 }} />
                Profile
              </MenuItem>
              <Divider />
              <MenuItem onClick={handleLogout}>
                <LogoutIcon sx={{ mr: 1, fontSize: 20 }} />
                Logout
              </MenuItem>
            </Menu>
          </Box>
        )}
      </Toolbar>
    </AppBar>
  )
}
