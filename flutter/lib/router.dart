import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'features/auth/auth_state.dart';
import 'features/auth/change_password_screen.dart';
import 'features/auth/login_screen.dart';
import 'features/data/data_screen.dart';
import 'features/home/home_screen.dart';
import 'features/match_detail/match_detail_screen.dart';
import 'features/matches/matches_screen.dart';
import 'features/profile/profile_screen.dart';
import 'features/shell/main_shell.dart';
import 'features/team_detail/team_detail_screen.dart';

final _rootKey = GlobalKey<NavigatorState>();
final _shellKey = GlobalKey<NavigatorState>();

final routerProvider = Provider<GoRouter>((ref) {
  final authNotifier = ref.read(authProvider.notifier);

  return GoRouter(
    navigatorKey: _rootKey,
    initialLocation: '/home',
    refreshListenable: authNotifier.authListenable,
    redirect: (context, state) {
      final auth = ref.read(authProvider);
      if (!auth.initialized) return null;

      final loc = state.matchedLocation;
      final loggingIn = loc == '/login';
      final changingPwd = loc == '/change-password';

      if (!auth.isAuthenticated) {
        return loggingIn ? null : '/login';
      }
      if (auth.mustChangePassword) {
        return changingPwd ? null : '/change-password';
      }
      if (loggingIn || changingPwd) {
        return '/home';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/change-password',
        builder: (context, state) => const ChangePasswordScreen(),
      ),
      GoRoute(
        path: '/teams/:id',
        parentNavigatorKey: _rootKey,
        builder: (context, state) {
          final id = state.pathParameters['id']!;
          return TeamDetailScreen(teamId: id);
        },
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) {
          return MainShell(navigationShell: navigationShell);
        },
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/home',
                builder: (context, state) => const HomeScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            navigatorKey: _shellKey,
            routes: [
              GoRoute(
                path: '/matches',
                builder: (context, state) => const MatchesScreen(),
                routes: [
                  GoRoute(
                    path: ':id',
                    parentNavigatorKey: _rootKey,
                    builder: (context, state) {
                      final id = state.pathParameters['id']!;
                      return MatchDetailScreen(matchId: id);
                    },
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/data',
                builder: (context, state) => const DataScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/profile',
                builder: (context, state) => const ProfileScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
  );
});
