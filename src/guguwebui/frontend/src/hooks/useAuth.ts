import { useAuthContext } from '../context/AuthContext'

export function useAuth() {
  return useAuthContext()
}