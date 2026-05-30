import Foundation
import XCTest
@testable import AICaddie

final class CoursePrepTests: XCTestCase {
    func testDecodesPrepResponse() throws {
        let json = """
        {"schema":"ai-caddie-course-prep-v1","globalId":31870,"holeCount":1,
         "clubs":[{"name":"1W","m":200,"yd":219},{"name":"7I","m":128,"yd":140}],
         "holes":[{"hole":1,"par":5,"par_source":"played","blue_yards":523,"route_len_m":478.4,
           "steps":[{"club":"1W","note":"开球落点约 219y"},{"club":"7I","note":"剩约 140y 上果岭"}],
           "cautions":["果岭边沙坑（约 480y）——别短别偏"],
           "landing_m":200.0,"tee_club":"1W",
           "hazards":{"water_carry":[],"bunkers":[[440.0,12.0]]},
           "map":{"image":"data:image/jpeg;base64,AAAA","overlay":{"w":720,"h":1120,"ppm":1.2,"ln":478.4,"route":[[100.0,1000.0,0.0],[200.0,100.0,478.4]]}}}]}
        """
        let response = try JSONDecoder().decode(CoursePrepResponse.self, from: Data(json.utf8))
        XCTAssertEqual(response.globalId, 31870)
        XCTAssertEqual(response.holeCount, 1)
        XCTAssertEqual(response.clubs.first?.name, "1W")
        XCTAssertEqual(response.clubs.first?.yd, 219)

        let hole = try XCTUnwrap(response.holes.first)
        XCTAssertEqual(hole.par, 5)
        XCTAssertEqual(hole.parSource, "played")
        XCTAssertEqual(hole.blueYards, 523)
        XCTAssertEqual(hole.teeClub, "1W")
        XCTAssertEqual(hole.steps.count, 2)
        XCTAssertEqual(hole.hazards.bunkers.first, [440.0, 12.0])
        XCTAssertEqual(hole.map?.overlay.route.count, 2)
        XCTAssertEqual(hole.map?.overlay.ln, 478.4, accuracy: 0.01)
    }

    func testOptionalFieldsTolerateAbsence() throws {
        // map/landing_m/tee_club absent (e.g. render=false or a par-3 with no landing)
        let json = """
        {"schema":"ai-caddie-course-prep-v1","globalId":1,"holeCount":1,"clubs":[],
         "holes":[{"hole":3,"par":3,"par_source":"estimate","blue_yards":167,"route_len_m":153.5,
           "steps":[{"club":"7I","note":"约 167y 到果岭中心"}],"cautions":[],
           "landing_m":null,"tee_club":"7I","hazards":{"water_carry":[[40.0,90.0]],"bunkers":[]}}]}
        """
        let response = try JSONDecoder().decode(CoursePrepResponse.self, from: Data(json.utf8))
        let hole = try XCTUnwrap(response.holes.first)
        XCTAssertNil(hole.landingM)
        XCTAssertNil(hole.map)
        XCTAssertEqual(hole.hazards.waterCarry.first, [40.0, 90.0])
    }
}
